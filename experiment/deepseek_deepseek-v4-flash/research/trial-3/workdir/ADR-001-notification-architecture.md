# ADR-001: Notification Architecture — Redis Streams for Asynchronous Notifications

## Status

Proposed

## Context

The notifier subsystem currently sends emails and webhooks synchronously inside the Flask request cycle. This produces four concrete failure modes:

1. **Request timeouts** — notification I/O blocks the response (avg 800 ms, spikes to 8 s at peak).
2. **Silent failures** — a down email provider or webhook endpoint drops the notification with no retry and no dead-letter.
3. **Cascading failures** — two incidents this year where a slow webhook exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical events ("trial expired", "payment failed") require exactly-once delivery; today they get none.

Targets: decouple notifications from the request cycle; retry with exponential backoff; at-least-once delivery for billing events with exactly-once where feasible; WebSocket push within two quarters; 10× traffic growth without re-architecting.

Constraints that shape this decision:

- Engineering team of 6 (3 senior, 3 mid), **no dedicated infrastructure engineer**.
- **Redis already runs in production** (session storage, rate limiting).
- **No Kafka experience on the team.**
- Value must land within **2 weeks** of setup/migration work.
- **Modest budget** — managed Confluent Cloud at full scale is out of reach.
- Exactly-once semantics must be maintained for billing notifications.

## Decision

**Adopt Redis Streams as the notification transport.** Flask request handlers `XADD` notification events to per-stream queues and return immediately; worker consumers process email/webhook delivery via Redis consumer groups (`XREADGROUP`/`XACK`) with retry, exponential backoff, and a dead-letter stream. This option satisfies every constraint within the 2-week window using infrastructure the team already operates. The Redis docs themselves describe this fit: Streams exist to "replace a dedicated Kafka deployment for moderate-scale, short-retention streaming workloads using infrastructure you already run" (redis.io/docs/latest/develop/use-cases/streaming/).

### Why Redis Streams wins on the deciding axes

| Axis | Redis Streams (chosen) | Apache Kafka (rejected) | Verdict |
|---|---|---|---|
| **Throughput** | A single Redis node sustains on the order of 10⁵ ops/s or more for simple stream operations; `XADD` is O(1). Our load — ~2M tasks/month, low single-digit notification events/s on average, low hundreds/s at peak, ~10³/s at 10× — is a rounding error. | Millions of messages/s in Confluent's published benchmarks. Headroom we do not need and cannot afford to operate. | Redis more than sufficient; Kafka is overkill. |
| **Ordering** | Per-stream FIFO with monotonically increasing message IDs. Per-entity order is preserved by routing all events for one entity (task/tenant) to one stream. | Per-partition ordering; global order requires a single partition, which kills parallelism. | Equivalent for our use case. |
| **Message retention** | In-memory log, bounded with `MAXLEN`/`MINID` trimming. Sufficient for a work queue: events are consumed and acked in seconds; the DLQ is drained on a schedule. | Disk-backed, time/size-based retention with full replay and audit. | Redis sufficient; Kafka's replay is a nice-to-have, not a requirement. |
| **Consumer groups** | Native: `XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`/`XAUTOCLAIM` — exactly the retry/DLQ pattern we need, with crash recovery of unacknowledged entries. | Native, offset-based with consumer rebalancing — a larger model to learn and tune. | Redis covers the requirement with less machinery. |
| **Exactly-once semantics** | Not provided end-to-end; consumer-side idempotency (dedupe on event ID) is required. | Kafka's EOS (idempotent producer + transactions, since 0.11.0.0) is **intra-Kafka only** — consuming from a topic and producing to another (e.g., Kafka Streams). Confluent's guidance for external sinks is to write the transactional output to a topic, then "rely on idempotence as you propagate that data to the external system." Our sinks — an email provider and HTTP webhooks — are **outside the broker**. | Tie. Both require idempotent consumers for real exactly-once. Kafka's EOS does not solve our billing problem; a unique event-ID dedupe does. |
| **Operational complexity** | Zero new infrastructure — Streams are a data type in the Redis we already run (since 5.0). Same client, same monitoring, same runbooks. | New cluster (self-hosted with KRaft, or AWS MSK), new client stack, partition/rebalance/offset management, monitoring, upgrades — for a 6-person team with no Kafka experience. | **Decisive.** Kafka alone blows the 2-week budget. |

### How the billing exactly-once requirement is actually met

Neither broker can make an external call exactly-once — a webhook endpoint or email provider cannot participate in a broker transaction. The requirement is met the same way on either platform:

1. The producer assigns a unique event ID and retries `XADD` on failure (at-least-once on the wire).
2. The consumer records the event ID in Postgres with a unique constraint **before** sending (or after, with an idempotency key), so a duplicate delivery attempt is detected and skipped.
3. `XAUTOCLAIM` (Redis ≥ 6.2) recovers entries from crashed consumers; `XPENDING` surfaces stragglers; after N retries the event moves to a dead-letter stream for operator review.

This yields effectively-exactly-once for billing without depending on broker-level transactions that cannot extend to external sinks.

### WebSocket push (2-quarter target)

Redis Streams' blocking reads (`XREAD BLOCK`) and the existing Redis pub/sub used for session fan-out map directly onto a WebSocket gateway — a pattern the team can reuse from the session/rate-limit Redis already in place. Kafka would require standing up a separate gateway and topic topology for the same result.

## Consequences

### Positive

- **Fast time-to-value:** producer/consumer change is a client-side refactor; no new service to stand up. A working version lands inside the 2-week constraint.
- **Solves all four failure modes:** request cycle decoupled (timeouts gone); retries + DLQ (silent failures gone); bounded worker concurrency (cascading failures gone); idempotent billing delivery (guarantees restored).
- **Operational fit:** the team already runs Redis for sessions and rate limiting — same client library, same monitoring, same runbooks. No new infra engineer required.
- **Cheap:** no managed-Kafka spend; a modest RAM increase on the existing Redis (or a small dedicated instance) covers it.
- **Adequate headroom:** 10× growth lands at ~10³ events/s peak, far below a single Redis node's ceiling. Redis Cluster or client-side sharding (partition by stream) is a later, incremental step — not a re-architecture.
- **Ordering preserved** per task/entity via stream routing; message IDs are monotonically increasing, which helps debugging and replay within the retention window.

### Negative

- **Memory-bound retention:** streams live in RAM. `MAXLEN` trimming and DLQ draining are mandatory operational discipline; a misconfigured stream can grow without bound.
- **Single-node throughput ceiling:** a single Redis instance is largely single-threaded for command execution. True scale-out requires Redis Cluster or explicit client-side sharding — fine at 10×, a real constraint at 100×.
- **Weaker durability than Kafka:** with AOF `appendfsync everysec`, a crash can lose up to ~1 s of unacknowledged writes. Mitigated by producer retry + event-ID dedupe (at-least-once holds), but it is a real, documented trade-off vs. Kafka's replicated disk log.
- **No built-in replay/audit:** once trimmed, history is gone. If long-term audit of every notification becomes a requirement, we must archive to Postgres or S3 alongside the stream.
- **Broker-level exactly-once does not exist:** the team must build and maintain the idempotency layer. This is unavoidable on either platform, but it is a standing piece of code, not a free feature.
- **No schema governance:** no Schema Registry equivalent; we enforce event schemas by convention and validation. Acceptable at this team size.

## Alternatives Considered

### Apache Kafka — rejected

Kafka is the industry-standard event log and its strengths are real: disk-backed retention with replay, partition-based parallelism at massive scale, strong replicated durability, and a rich ecosystem. It is the right answer for a platform that needs a durable, queryable, multi-year event history or cross-team analytics pipelines.

It fails this decision on the binding constraints:

- **Operational complexity vs. team size:** self-hosting Kafka (KRaft or ZooKeeper, broker sizing, partition/rebalance management, offset management, monitoring, upgrades) is close to a full-time operational job; MSK reduces but does not eliminate it. A 6-person team with **zero Kafka experience and no infra engineer** would burn well past the 2-week budget standing it up and learning it — before writing any notifier code.
- **Cost:** managed Confluent Cloud at scale is explicitly out of budget. Even MSK adds meaningful spend for headroom we will not use.
- **Throughput is the wrong axis:** our 10× target (~10³ events/s peak) is comfortably within Redis' range. Kafka's millions of msg/s is unused capacity we would pay for in money and complexity.
- **Exactly-once does not transfer:** Kafka's transactions guarantee exactly-once only between Kafka producers and consumers (Streams API). Our sinks are external (email, webhooks), so the billing requirement still needs the same idempotent-consumer code we would write on Redis — Kafka's flagship feature buys us nothing here.
- **Ordering and consumer-group needs are already met** by Redis Streams for this workload.

**Revisit trigger:** adopt Kafka (or a managed equivalent) when (a) sustained notification volume approaches a single Redis node's ceiling (>~10⁵ events/s, roughly 100× current), (b) multi-year replay/audit of the full event history becomes a requirement, (c) multiple independent teams/services need to consume the same event log with independent retention, or (d) cross-region replication becomes a hard requirement. The producer/consumer API shapes are similar enough that migration is a transport swap, not a rewrite — which is why choosing Redis first does not paint us into a corner.

### Status quo (synchronous delivery) — rejected

Keeping notifications in the request path is the direct cause of all four failure modes (timeouts, silent drops, pool exhaustion, no guarantees). It requires no new infrastructure and therefore was tempting, but it fails every stated scaling target. It is not a viable option; it is the problem we are solving.
