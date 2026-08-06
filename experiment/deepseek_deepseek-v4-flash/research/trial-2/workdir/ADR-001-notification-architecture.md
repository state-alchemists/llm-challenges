# ADR-001: Notification Subsystem — Use Redis Streams for Asynchronous Notification Delivery

## Status

Proposed

## Context

We operate a SaaS project management platform (85,000 MAU, ~2M tasks/month, ~500 req/s at peak) on a Python/Flask monolith with PostgreSQL (single primary + one read replica), four web servers behind nginx, and Redis for session storage and rate limiting. Notifications — emails and webhooks on task update, assign, and complete — are sent synchronously inside the HTTP request cycle. This has produced four concrete problems:

1. **Request timeouts**: sending blocks the response; average latency is 800ms with spikes to 8s during peak hours.
2. **Silent failures**: when an email provider or webhook endpoint is down, the notification is silently dropped — no retry, no dead-letter queue.
3. **Cascading failures**: twice this year a slow webhook endpoint exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees**: billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once; today they can be lost or duplicated.

We must decouple notifications from the HTTP request cycle and, within the next two quarters: support retry with exponential backoff, guarantee at-least-once delivery for billing events with exactly-once where feasible, add real-time WebSocket push, and handle 10x traffic growth without re-architecting.

Constraints that shape this decision:

- Engineering team is 6 people (3 senior, 3 mid-level), with **no dedicated infrastructure engineer**.
- **Redis is already in production** (sessions, rate limiting).
- **No Kafka experience anywhere on the team**.
- The first version must deliver value within **2 weeks** of setup/migration work.
- Budget is modest: managed Confluent Cloud at full scale is out of reach today.

Volume reality check (estimates): ~2M task events/month, each generating 2–4 notifications, is roughly 2–4 events/s on average and tens to low hundreds/s at peak today. At 10x, even an aggressive ceiling — every one of 5,000 peak req/s producing two notifications — is ~10,000 events/s. This is the number to size against.

## Decision

Adopt **Redis Streams** on a dedicated Redis instance as the notification transport. The stream is the delivery buffer between the monolith and notification workers; PostgreSQL remains the system of record.

Mechanism, and how each requirement is met:

- **Async decoupling**: task handlers append an event with `XADD` and return; a worker pool reads with consumer groups (`XREADGROUP`) and performs the send. HTTP latency drops back to DB-only.
- **At-least-once**: consumer groups track every delivered-but-unacknowledged entry in the pending entries list (PEL). A worker that crashes before `XACK` leaves the entry pending; `XAUTOCLAIM` (Redis 6.2+) re-claims it for another worker after a visibility timeout.
- **Retry with exponential backoff**: failed entries are not acked; a retry worker re-claims them with increasing delay, then moves them to a dead-letter stream after N attempts (driven off `XPENDING` monitoring).
- **Exactly-once for billing (effectively)**: end-to-end exactly-once is not a broker property in any queue — it is built with idempotent consumers. Events are written to a transactional outbox table in the same Postgres transaction as the task update; a relay publishes them to the stream; the consumer checks `event_id` against a unique index in Postgres before acting. Duplicates are rejected at the unique constraint, so billing side effects happen exactly once. Outbound billing webhooks carry an idempotency key.
- **WebSocket push**: a stream supports multiple independent consumer groups, so the real-time gateway worker runs its own group off the same stream.

Why Redis Streams wins for this team and scale:

- **Operational complexity is the deciding constraint.** Kafka is a distributed system that must be operated: a 3-broker minimum cluster, KRaft (or ZooKeeper), partition/replication design, rebalancing, lag monitoring, and involved upgrades. With no infra engineer, no Kafka experience, and a 2-week budget, that is a standing tax this team cannot pay. Redis Streams adds one small instance and a handful of commands (`XADD`, `XREADGROUP`, `XACK`, `XAUTOCLAIM`, `XINFO`) to a technology the team already runs in production — value in days, not weeks.
- **Throughput**: a single Redis instance sustains ~100k+ stream ops/s on modest hardware. The 10x ceiling of ~10k events/s is an order of magnitude under that. Kafka's millions-of-messages/s capability is three orders of magnitude beyond the requirement and would be pure overhead.
- **Cost**: one small dedicated instance versus a 3-broker Kafka cluster; Confluent Cloud is explicitly out of budget.
- **Ordering**: Redis Streams gives strict order within a stream, matching Kafka's per-partition ordering. Shard by task/user hash (one stream per bucket) when per-entity order matters — the same partitioning technique Kafka would require.
- **Retention**: the stream is a bounded delivery buffer, not the system of record. `MAXLEN` with approximate trimming bounds memory; billing durability lives in the Postgres outbox, so the stream only needs enough retention to cover retry windows. If long-term replay is ever needed, raw events archive to S3.

A dedicated instance (rather than sharing the session cache) is deliberate: it isolates the stream from cache eviction policies and memory pressure, and keeps a slow consumer from competing with session traffic for the same keyspace.

## Consequences

### Pros

- **Near-zero new operational surface**: same Redis tooling, runbooks, and muscle memory the team already has.
- **Fits the 2-week constraint**: instance + outbox relay + consumer worker + retry loop is days of work.
- **Modest cost**: one small instance; no broker minimums, no per-partition charges.
- **Comfortable throughput headroom** at 10x target (~10k events/s vs ~100k+ ops/s capacity).
- **At-least-once for free**: native consumer groups with PEL delivery tracking.
- **Independent scaling per consumer**: multiple consumer groups per stream let email, webhook, and future WebSocket workers scale and backpressure independently.
- **Billing exactly-once is not forfeited**: it is achieved with the same consumer-side idempotency machinery any broker choice would require.
- **WebSocket push slots into the same bus** within the 2-quarter window.

### Cons

- **Single-writer bottleneck**: one Redis primary is the write point; there is no Kafka-style horizontal broker scaling. Fine at this scale (10x is still an order of magnitude below capacity), but it is a real ceiling — a future re-architecture if we ever need millions of events/s or multi-region writes.
- **Retention is RAM-bound**: long replay windows are expensive in memory; we mitigate with `MAXLEN`, prompt acking, and S3 archival, but Kafka's disk-based retention would be cheaper for months-long replay.
- **No native dead-letter queue**: dead-lettering must be built with `XPENDING`/`XCLAIM` plus a monitor worker — small, but ours to write and test.
- **Exactly-once is consumer-side discipline**: the guarantee holds only while the idempotent-consumer pattern is followed; a future consumer that skips dedup silently regresses to at-least-once (duplicate emails/webhooks).
- **Weak cross-region story**: Redis replication does not give Kafka-grade active-active multi-datacenter semantics; acceptable for a single-region deployment, a gap if we globalize.
- **New API surface**: the team must learn Streams semantics (consumer groups, PEL, `XCLAIM`) — small compared with learning Kafka, but real.

## Alternatives Considered

### Apache Kafka — rejected

Kafka is the stronger product on paper, and each of its advantages was weighed:

- **Throughput**: millions of messages/s per cluster — an order of magnitude beyond what a 10x-grown workload needs. No benefit at our scale; capacity we would never use.
- **Ordering**: per-partition ordering — the identical model to Redis Streams sharding; we would need the same partitioning design either way, so this buys nothing here.
- **Retention**: disk-based, configurable in days/weeks — genuinely better than RAM-bound streams for long replay. This is the one technical point Kafka wins outright, and it does not matter for our requirements: the Postgres outbox is the durable record, and the stream only needs to cover retry windows.
- **Consumer groups**: mature and native, but rebalancing is its own operational surface (partition assignment, consumer lag, rebalance storms) that the team would have to learn from scratch.
- **Exactly-once (EOS)**: transactional producer/consumer semantics (KIP-98) provide stronger broker-side atomicity. However, end-to-end exactly-once still requires an idempotent transactional sink — the same consumer-side idempotency we are building on Redis. Kafka's transactional machinery (transactions, coordinators) adds complexity without removing that requirement.
- **Operational complexity — the disqualifier**: no team member has run Kafka, there is no infra engineer, and the constraint is 2 weeks to value. Standing up a 3-broker cluster (KRaft or ZooKeeper), designing topics/partitions, and building retry/dead-letter on top is more than 2 weeks of focused work — before the standing burden of brokers, disks, rebalancing, and upgrades lands on a 6-person product team. Managed options do not save us: MSK still charges per broker with a cluster minimum and we still must learn the semantic surface; Confluent Cloud is explicitly out of budget.

Verdict: Kafka is the right choice at 100x our scale with a dedicated infrastructure team. For this team, budget, and 2-week horizon, its guarantees are purchased with an operational cost we cannot pay, for capacity we cannot use.
