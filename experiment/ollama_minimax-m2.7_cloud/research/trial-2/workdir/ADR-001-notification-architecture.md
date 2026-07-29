# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

The notification module currently executes synchronously inside the Flask HTTP request cycle, causing request timeouts (avg 800 ms, spikes to 8 s at peak), silent failures on downstream outages, cascading failures from slow webhook endpoints, and zero delivery guarantees for billing-critical events. We need to decouple notification dispatch, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), and scale to 10× current traffic without re-architecting.

**System constraints shaping this decision:**

| Constraint | Implication |
|---|---|
| 6-person team, no dedicated infra engineer | Operational complexity must be low |
| No Kafka experience | Kafka carries significant learning-curve risk |
| 2-week max migration window | Must deliver value quickly, not "eventually" |
| Redis already in production | Incremental infra is cheaper than net-new |
| Peak ~500 req/s; 10× target ~5,000 req/s | Neither Kafka nor Redis Streams is throughput-constrained here |
| Exactly-once for billing events | Neither provides true exactly-once out of the box; both require idempotency logic |

**Non-functional requirements:**

- Decouple from HTTP request cycle (async processing)
- Retry with exponential backoff
- Dead-letter handling for permanent failures
- Support email, webhook, and future WebSocket push channels
- Handle 10× traffic growth (~5,000 req/s peak)

---

## Decision

**Choose Redis Streams as the notification message broker.**

The decision is driven by the team's constraints (size, expertise, time budget) and the fact that Redis is already in production. Redis Streams gives us async processing, consumer groups with acknowledgment, per-stream ordering, and configurable retention — all at a fraction of Kafka's operational overhead. The two-week constraint and lack of infra engineering bandwidth are disqualifying factors for Kafka's complexity.

---

## Consequences

### Benefits of Redis Streams

1. **Operational simplicity**: Redis is already running. No new service to deploy, monitor, or troubleshoot. The team manages one fewer system.
2. **Fast onboarding**: Consumer groups (`XREADGROUP`), acknowledgment (`XACK`), and pending entry lists (`XPENDING`) are well-documented and directly map to the retry/DLQ pattern we need. A mid-level engineer can implement a working producer/consumer in hours.
3. **Sufficient throughput**: At peak ~500 req/s today and a 10× target of ~5,000 req/s, Redis Streams comfortably handles this on the existing Redis instance (typical throughput: 50,000–100,000 msg/s per node). Kafka's million-msg/s ceiling is overkill.
4. **Ordering per stream**: `XADD` preserves insertion order within a stream. For task-update notifications on the same `task_id`, this gives us the ordering guarantee we need without partition management.
5. **Consumer groups for parallel processing**: Multiple workers can claim messages independently via `XREADGROUP`. Group state (last acknowledged ID) is maintained by Redis — no external offset store needed.
6. **Dead-letter via separate stream**: A failed notification after max retries is moved to a `notifications.dlq` stream. Operators can inspect and replay from there.
7. **Existing session/rate-limiting footprint**: Redis is already in the critical path for auth. Using it for notifications does not meaningfully increase operational risk; a Redis outage already takes down auth anyway.

### Drawbacks / Mitigations

1. **No native exactly-once semantics**: Redis Streams provides at-least-once with `XACK`. Achieving exactly-once requires idempotency keys in the consumer (e.g., store a deduplication window in Redis or Postgres keyed on `notification_id + event_id`). This is acceptable given the requirement states "exactly-once where feasible" — idempotency is the standard pattern.
2. **Message retention is bounded**: Redis Streams trims via `MAXLEN ~` (approximate trimming) or `MINID`. Retention is not infinite like Kafka's log-based model. For billing events, we mitigate by processing the DLQ within 7 days and persisting confirmed notifications to Postgres immediately after `XACK`.
3. **No nativecompaction**: Kafka's log compaction is useful for caching latest values per key. Redis Streams has no direct equivalent. We do not need this for the notification use case.
4. **Single-node throughput ceiling (without cluster)**: Single-instance Redis Streams scales to ~100k msg/s. For a 5,000 req/s target, this is 20× headroom — not a near-term concern. Redis Cluster would be the upgrade path beyond ~500k msg/s.
5. **Less ecosystem tooling**: Kafka has battle-tested connectors (Kafka Connect), schema registry, and stream processing (Kafka Streams). For our scope — email + webhook + future WebSocket — Redis Streams is sufficient without that ecosystem.

---

## Alternatives Considered

### Apache Kafka

Kafka would be the correct choice if any of the following were true:

- The team had dedicated infrastructure engineers or prior Kafka experience.
- The scaling target were 100,000+ msg/s sustained.
- We needed log compaction, multi-region replication, or Kafka Connect sinks.
- The migration window were 2 months instead of 2 weeks.

In our current situation, Kafka's advantages do not materialize:

| Factor | Kafka | Redis Streams |
|---|---|---|
| Throughput ceiling | Millions of msg/s | ~100k msg/s per node |
| Exactly-once | Native transactional producers/consumers | Requires idempotency logic |
| Ordering | Per-partition | Per-stream |
| Consumer groups | Native | Native (XREADGROUP) |
| Retention | Days/weeks/months (configurable) | Bounded (MAXLEN/MINID) |
| Operational complexity | High (brokers, ZooKeeper/KRaft, replication tuning, partition management) | Low (Redis already running) |
| Learning curve | High (no team experience) | Low (team uses Redis today) |
| Infra required | New cluster | Existing Redis instance |
| Time to first value | 2–6 weeks | 2–5 days |

Kafka's **exactly-once semantics** (EOS) are genuinely stronger than Redis Streams' at-least-once + idempotency pattern, and this matters for billing notifications. However, the implementation gap is smaller than it appears: a Postgres-backed idempotency table (storing `event_id` with a unique constraint and a TTL) achieves the same guarantee for billing events at a fraction of Kafka's complexity. The risk of misconfiguring Kafka partitions, replication factors, and consumer group offsets — without experience — is higher than the risk of a well-designed idempotency layer.

---

## Recommendation

Implement the notification subsystem on **Redis Streams**. The team's constraints (size, expertise, timeline, existing Redis footprint) make Kafka's operational burden a disqualifying factor despite its superior throughput ceiling and native exactly-once support. Redis Streams provides sufficient throughput, correct ordering semantics, consumer group orchestration, and DLQ support within days of work. Exactly-once delivery for billing events is achieved via an idempotency key stored in Postgres alongside the notification record.

The implementation path:

1. Add a `notifications.pending` stream (and `notifications.dlq` for failures).
2. Refactor notification dispatch to `XADD` into the stream instead of executing inline.
3. Introduce a background worker that `XREADGROUP` from the stream, dispatches, and `XACK`s on success or routes to DLQ after max retries.
4. Add an idempotency check (query Postgres by `event_id`) before dispatching to cover the exactly-once requirement for billing events.
5. Instrument with Redis `XLEN` (stream length) and `XPENDING` (pending count) metrics for observability.

This delivers value within the two-week window and positions us to add WebSocket push (via a separate stream consumer) within the target quarter.
