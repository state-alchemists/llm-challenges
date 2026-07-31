# ADR-001: Notification Subsystem — Message Broker Choice

**Status:** Proposed

## Context

We run a SaaS project-management platform with 85,000 monthly active users, roughly 2 million tasks created per month, and a sustained peak of ~500 requests/second during business hours (system_context.md:5-8). Today the notification module — email and webhook delivery on task update/assign/complete events — runs synchronously inside the Flask request cycle (system_context.md:16).

That coupling is the source of four production problems (system_context.md:22-25):

1. **Request timeouts.** Sending notifications blocks the response: average latency is 800 ms, spiking to 8 s at peak.
2. **Silent failures.** A down email provider or webhook endpoint drops the notification; there is no retry and no dead-letter queue.
3. **Cascading failures.** Two incidents this year: a slow webhook exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees.** Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, but the current system guarantees nothing.

The target architecture (system_context.md:29-34) must: decouple notification dispatch from the request cycle; retry with exponential backoff; guarantee at-least-once delivery for billing events (exactly-once where feasible); support real-time WebSocket push within two quarters; and absorb 10x traffic growth without re-architecting.

The constraints that bind the choice (system_context.md:38-43):

- Engineering team of six (three senior, three mid-level) with **no dedicated infrastructure engineer**.
- Redis already runs in production for sessions and rate limiting — the team knows how to operate it.
- **No Kafka experience** on the team today.
- No more than **two weeks** of setup/migration work before delivering value.
- Modest budget: managed Confluent Cloud is not affordable at full scale.
- Exactly-once semantics must be maintained for billing notifications.

## Decision

We will **use Redis Streams** as the asynchronous message backbone for the notification subsystem.

Concretely: the Flask app becomes a producer — on task events it writes a notification record to a Redis stream with `XADD` and returns immediately (milliseconds instead of 800 ms). Dedicated consumer workers (separate processes, scaled independently of the web servers) read with `XREADGROUP`, dispatch to email/webhook/WebSocket adapters, and `XACK` on success; failures are retried with exponential backoff and routed to a dead-letter stream after N attempts. Billing notifications carry an idempotency key (e.g., `notification_id`) that the consumer deduplicates against a unique constraint in Postgres — that consumer-side dedup is what delivers the "exactly once" guarantee.

This choice is driven by the constraints, not by feature envy. Weighing the properties that matter here:

- **Operational complexity (decisive).** Kafka is a distributed system that demands a broker cluster, KRaft/ZooKeeper coordination, partition/replication tuning, JMX monitoring, and offset/rebalance troubleshooting — a serious operational load for a six-person team with no infrastructure engineer and no Kafka experience. Redis Streams runs on infrastructure we already operate: `XADD`/`XREADGROUP`/`XACK` are calls through the same `redis-py` client we already use for sessions and rate limiting. This is the difference between days and weeks-to-months of operational runway; it alone satisfies the two-week constraint and directly mitigates the team-size risk that Kafka's complexity would introduce.

- **Throughput.** Kafka's multi-million-messages-per-second throughput is real but irrelevant here. Our 10x target is ~5,000 requests/second peak, and notifications are only a subset of that traffic. A single Redis node comfortably sustains tens to hundreds of thousands of small messages per second (an order-of-magnitude engineering estimate, not a benchmark claim) — 10–50x the headroom we need. We are not volume-bound; we are time-to-value bound.

- **Ordering guarantees.** A Redis stream is an append-only log: entries are totally ordered within the stream, and a consumer group hands each entry to exactly one consumer in order. That covers our real requirement — per-task notification ordering. Kafka's per-partition ordering with keyed partitioning is stronger only when strict order must be preserved across very large parallel fan-out, a scale we do not have.

- **Message retention.** Redis Streams retains entries until trimmed (`MAXLEN`/`MINID`). We will enforce a bounded retention window (e.g., 7 days, capped by `MAXLEN`) — enough for replay of a stuck consumer and a dead-letter audit trail. Kafka's disk-log retention with log compaction is genuinely superior for long-lived audit replay, but we have no requirement to replay months of notification history; spending cluster resources on that capability would be speculative.

- **Consumer groups.** Both products provide consumer groups. Redis Streams groups add a per-consumer pending-entries list (PEL): unacknowledged entries stay visible via `XPENDING` and can be reclaimed with `XCLAIM`/`XAUTOCLAIM` when a worker dies — at-least-once delivery with simple, debuggable mechanics. Kafka's consumer groups are more feature-rich (automatic rebalancing, committed offsets) but bring exactly the rebalance complexity our team would have to babysit.

- **Exactly-once semantics.** The honest engineering answer is that **neither broker delivers end-to-end exactly-once to an external side effect** such as sending an email or firing a webhook. Kafka's exactly-once semantics (idempotent producer + transactions) guarantee atomicity only inside Kafka-to-Kafka pipelines; they cannot make an email provider accept a delivery exactly once. Redis Streams likewise offers at-least-once and no more. The billing guarantee therefore comes from the consumer, not the broker: at-least-once delivery plus an idempotency key enforced by a unique constraint in Postgres. This pattern works identically on top of either option, so Kafka's headline exactly-once feature does not actually tip the scale for our requirement.

## Consequences

**Positive.** We get a working subsystem in roughly one week: producers, consumers, retry with backoff, dead-letter stream, and idempotent billing delivery. Operational risk stays where the team already has competence — Redis monitoring, memory policies, the existing backup runbook — and no new infrastructure line item appears. Request latency drops to the milliseconds the database needs; the connection-pool cascade failure mode disappears because webhook calls no longer run inside request handlers. At-least-once delivery with visible in-flight state (`XPENDING`) gives us debugging observability the current silent-drop system lacks. The same streams back the WebSocket push work in two quarters: gateway processes consume the stream and fan out to sockets, with a replay buffer for late-joining clients. Durability is inherited from Redis persistence (AOF), so a node restart does not silently lose queued notifications.

**Negative / trade-offs.** Streams live in RAM, so retention is memory-bound: we must enforce `MAXLEN`/`MINID` discipline, and a dedicated Redis instance (or at least a separate logical database with its own memory budget) is required so notification traffic cannot evict sessions or rate-limit state — a small but real cost and a new operational responsibility. A single Redis node is a scaling ceiling: beyond it we must shard by stream key manually, because there is no automatic partition-rebalance story like Kafka's. There is no native log compaction or time-based retention, so long-term replay is off the table by design. Exactly-once requires the consumer-side idempotency machinery to be built correctly — if the unique constraint is missed, duplicates slip through. And the choice is not immortal: if sustained throughput or retention needs ever exceed a single node's practical envelope, we will need to migrate to a broker (likely Kafka). We accept this and isolate the broker behind a thin producer/consumer abstraction now so the swap remains possible.

## Alternatives Considered

**Apache Kafka** — rejected for this team, at this scale, on this timeline. Its strengths are real: very high throughput, disk-log retention with log compaction for long-lived replay, mature consumer-group rebalancing, and exactly-once semantics for stream processing. But none of them pays off here. The operational burden — standing up and babysitting a broker cluster with no infrastructure engineer and no in-house Kafka experience, inside a two-week budget — is disqualifying on its own. The cost picture is disqualifying too: managed Confluent Cloud is explicitly out of budget, and self-hosted Kafka (or Amazon MSK) adds meaningful infrastructure and admin cost for capability we will not exercise. Its headline exactly-once feature does not extend to the external email/webhook side effects our billing guarantee actually protects, so it does not simplify the hardest requirement. We are not dismissing Kafka permanently: the abstraction boundary we build now is specifically the seam we would migrate across if growth (sustained throughput beyond a single node, multi-week replay requirements, heavy multi-group fan-out) eventually justifies the operational investment.
