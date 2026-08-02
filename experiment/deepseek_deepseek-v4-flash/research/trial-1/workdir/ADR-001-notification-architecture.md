# ADR-001: Notification Subsystem — Asynchronous Delivery with Redis Streams

**Status:** Proposed

## Context

We run a SaaS project management platform on a Python/Flask monolith (~50k lines) behind nginx on four AWS web servers, with PostgreSQL as the system of record and a single Redis instance used today for session storage and rate limiting. The notification module (email and webhook delivery on task update, assignment, and completion) currently runs synchronously inside the HTTP request cycle, and that design has become the bottleneck:

- **Request timeouts.** Notification delivery blocks the response; average latency is 800 ms and spikes to 8 s during peak hours.
- **Silent failures.** When an email provider or webhook endpoint is down, the notification is dropped. There is no retry and no dead-letter queue.
- **Cascading failures.** Twice this year a slow webhook endpoint exhausted the connection pool and took unrelated features down with it.
- **No delivery guarantees.** Billing-critical events ("trial expired", "payment failed") must not be lost or duplicated, and today they have no guarantee at all.

Over the next two quarters we must decouple notifications from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery for billing events with exactly-once where feasible, introduce real-time WebSocket push, and do it without re-architecting when traffic grows 10x.

The constraints are binding: an engineering team of six (three senior, three mid-level) with no dedicated infrastructure engineer; no Kafka experience in the team; a modest budget that rules out managed Confluent Cloud at full scale; and a requirement to deliver value within two weeks of setup/migration work. We already operate Redis in production.

## Decision

We will use **Redis Streams** for the notification subsystem, running on a dedicated Redis instance alongside the existing deployment.

The flow: after a task mutation commits to PostgreSQL, the Flask app appends a notification event to a stream with `XADD` outside the response path, so request latency no longer includes delivery. A small pool of worker processes consumes with `XREADGROUP`, performs the side effect (send email, POST webhook, or fan out to WebSocket gateways via Redis pub/sub), and acknowledges with `XACK`. A failed delivery stays in the consumer's pending-entries list (PEL) and is reclaimed after a configurable idle timeout with `XAUTOCLAIM` (available since Redis 6.2), giving retry with exponential backoff by escalating the idle threshold; entries that exceed N attempts are parked in a dead-letter stream for operator review.

We chose Redis Streams over Kafka for one overriding reason: it delivers the required guarantees at the workload's actual scale with infrastructure and skills we already have, while Kafka's superior ceiling is purchased with operational complexity this team cannot currently absorb.

**Throughput.** The workload is modest: 2M tasks/month averages to under a handful of events per second even counting several notifications per task, and at 10x growth sustained volume stays in the low hundreds per second at peak. A single Redis node sustains on the order of 100k+ operations per second, so we operate two to three orders of magnitude below the ceiling. Kafka's headline throughput (millions of events/sec on partitioned clusters) is real but irrelevant at this scale: it buys headroom we will not consume for years at a cost we would pay immediately.

**Ordering.** Streams are append-only logs: entries within a stream are strictly ordered, and a consumer reads them in order. Per-task ordering (assign → update → complete) is preserved by keying events to a per-task stream or accepting stream-level order and letting a single consumer own a task's lifecycle. Kafka gives stronger cross-consumer ordering through partition keys, but our requirement — a task's notifications fire in the order the user performed them — is met without it.

**Retention.** Redis Streams are memory-resident and trimmed (`MAXLEN`), so they act as a delivery queue, not an archive. Kafka keeps messages on disk for a configurable retention window and supports replay. For notifications this is acceptable: PostgreSQL remains the system of record, and any event we must re-deliver or audit lives in the database. We are not building the event log on the stream; we are using it as a transport.

**Consumer groups and delivery.** Both technologies provide consumer groups. Kafka manages offsets on the broker and rebalances members automatically; Redis tracks delivery state in the PEL, which yields at-least-once semantics: an entry stays pending until explicitly acknowledged, and a crashed worker's entries are reclaimed by others. The PEL doubles as a dead-letter ledger, since entries with a high delivery count are visible to `XPENDING`.

**Exactly-once.** This is the requirement most often cited in favor of Kafka, and it is where Kafka's advantage is smallest. Kafka's exactly-once semantics (idempotent producer plus transactions) guarantee exactly-once *within the broker's own log*; they cannot span an HTTP POST to a webhook or an email provider, and end-to-end exactly-once across external systems is impossible in any distributed system. The only way to make billing notifications exactly-once is an idempotent consumer: attach a unique event ID, record delivery atomically in PostgreSQL (a dedup table or a `delivered_at` transition), and treat any duplicate as a no-op. We will implement that pattern regardless of transport, so the billing requirement does not favor Kafka — it favors whichever transport makes idempotent retry cheapest to operate, which is the one we already run.

**Operational complexity.** This is the decisive axis. Self-hosted Kafka means standing up and operating a multi-broker cluster: KRaft metadata management (ZooKeeper was removed in Kafka 4.0), partition and replica leadership, disk sizing and replication policies, JMX-based monitoring, lag tracking, and careful rolling upgrades — a permanent second job for a team with no infrastructure engineer and no Kafka experience, and realistically more than the two-week budget to do safely. Managed Kafka (Confluent Cloud) exceeds the budget. Redis Streams, by contrast, is a data structure on a service we already run, monitor, and tune; the team already knows its failure modes. A dedicated stream instance isolates notification traffic from session/rate-limit workloads and lets us set an AOF persistence policy so undelivered messages survive restarts, which matters for at-least-once.

**Time to value.** Streams can be production-ready in days, not weeks: `XADD` on the write side, a small consumer loop with `XREADGROUP`/`XACK`/`XAUTOCLAIM` on the read side. That clears the two-week constraint comfortably and leaves room in the quarter for the WebSocket push, which reuses the same Redis footprint (pub/sub fan-out to gateway nodes).

## Consequences

**Pros.**

- Delivers within days on infrastructure and skills the team already has: no new service, no new failure domain, no Kafka learning curve.
- Well within capacity: two to three orders of magnitude of headroom at 10x growth.
- At-least-once delivery with retry (PEL + `XAUTOCLAIM`), dead-letter handling, and per-stream ordering out of the box.
- Exactly-once for billing achieved through idempotent consumers — a pattern we would need under Kafka anyway.
- Redis pub/sub gives a natural path to WebSocket push within the quarter.
- Low operational footprint: one more Redis instance the team already knows how to run.

**Cons.**

- Retention and durability are bounded by RAM: streams are trimmed and can be lost on a full instance failure unless AOF and replication are configured; they are not an audit log. Long replay of past events is not available — the database must cover that.
- Scale ceiling below Kafka: very high sustained throughput or many consumer groups will require sharding across streams and instances; single-node Redis is a potential scaling bottleneck and single point of failure (mitigate with a replica).
- No cross-stream global ordering; per-task ordering must be designed in.
- Exactly-once still depends on disciplined idempotency in our consumer code; the transport gives no free pass.
- The team owns stream hygiene: trimming policy, consumer-group lifecycle, DLQ review, poison-message handling.
- If traffic or retention needs outgrow Redis, migration to Kafka is the likely next step; we should keep the producer/consumer abstraction thin enough to make that move surgical.

## Alternatives Considered

**Apache Kafka (rejected for now).** Kafka is the technically stronger system on paper: disk-based retention with configurable replay, partitioning for horizontal scaling, broker-managed consumer groups with automatic rebalancing, and exactly-once semantics inside the ecosystem (idempotent producer plus transactions, KRaft-only since 4.x). It is the right tool for very high throughput, long retention, or multi-team event plumbing. It is the wrong tool for this team and this problem today: the requirement is a few hundred events per second with short-lived delivery state, and the team has no Kafka experience, no infrastructure engineer, and no budget for managed Kafka. Standing up a self-hosted cluster responsibly — KRaft configuration, partition/replica management, monitoring, disk planning, upgrade discipline — exceeds the two-week constraint and would consume scarce senior attention for quarters. Critically, Kafka does not actually solve the billing exactly-once requirement end-to-end; external side effects still need the same idempotent-consumer pattern. We will revisit Kafka if sustained throughput approaches Redis's ceiling, if we need long-duration replay or audit of the notification stream itself, or if the team grows an infrastructure function (or managed Kafka becomes affordable). This decision is revisit-worthy, not permanent.
