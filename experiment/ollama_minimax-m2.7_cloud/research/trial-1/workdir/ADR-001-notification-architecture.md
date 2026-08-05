# ADR-001: Notification Subsystem Messaging Backend

## Status

**Proposed**

## Context

### The Problem

The notification module (email + webhooks on task events) runs synchronously inside the HTTP request cycle. This has caused:

- **Request timeouts**: Mean latency 800 ms, spikes to 8 s at peak. Notifications block the response.
- **Silent failures**: Email provider or webhook downtime silently drops notifications. No retry, no dead-letter queue.
- **Cascading failures**: Two incidents where a slow webhook endpoint exhausted the connection pool, affecting unrelated features.
- **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly-once. The current system has no such guarantee.

### Constraints

| Constraint | Detail |
|---|---|
| Team size | 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer |
| Kafka experience | None on the team today |
| Existing infra | Redis already running (session storage + rate limiting) |
| Setup time | ≤ 2 weeks before delivering value |
| Budget | Modest; cannot afford managed Confluent Cloud at full scale |
| Exactly-once | Mandatory for billing notifications |
| Scale target | 10× traffic growth without re-architecture |

### Technical Requirements

1. Decouple notifications from the HTTP request cycle (async processing)
2. Retry with exponential backoff
3. At-least-once delivery minimum; exactly-once for billing events
4. WebSocket push notifications within 2 quarters
5. Handle 10× current traffic (~500 req/s → ~5,000 events/s at maturity)

---

## Decision

**Chosen option: Redis Streams**

Redis Streams is the correct choice given the team's size, existing Redis footprint, and the 2-week delivery constraint.

---

## Consequences

### Pros

- **Zero new infrastructure.** Redis is already running. The team manages one system instead of two.
- **Operational familiarity.** Six engineers already know Redis. No new mental model, no new runbooks, no on-call novelty.
- **2-week delivery is achievable.** Redis Streams requires no separate cluster provisioning, no broker configuration, no ZooKeeper/KRaft. A Python consumer process with `redis-py` and `XREADGROUP` is a weekend spike.
- **Sufficient throughput.** Current peak is ~500 req/s. Redis Streams on a well-connected EC2 instance handles tens of thousands of events per second. The 10× growth target (~5,000 events/s) is well within Redis Streams' capacity.
- **Message retention.** Redis Streams retain messages until explicitly trimmed (`MAXLEN`). Combined with consumer group acknowledgements (`XACK`), this gives at-least-once delivery out of the box.
- **Consumer groups.** `XREADGROUP` provides per-consumer-group offset tracking, fan-out to multiple consumers (email worker, webhook worker), and redelivery on failure — all standard Redis Streams primitives.
- **WebSocket roadmap.** Redis Pub/Sub integrates naturally with asyncio/websockets. A shared Redis instance means notification events can fan out to long-lived WebSocket connections with minimal additional infrastructure.

### Cons

- **Exactly-once requires deliberate implementation.** Redis Streams does not have native exactly-once semantics. Achieving it for billing events requires:
  - Idempotent consumers: store processed event IDs in a Redis set or PostgreSQL table and deduplicate before handling.
  - `XACK`-then-process or process-then-`XACK` ordering trade-off must be designed carefully (the standard pattern is process, store the event ID, then `XACK` — on restart, skip already-processed IDs).
  - This is not zero work, but it is well-understood and tractable for a senior engineer.
- **No native dead-letter queue.** Failed messages after max retries must be moved to a separate stream (`XREAD` from a DLQ stream) manually. This is a custom component the team must build.
- **Persistence depends on Redis durability.** If `appendonlyfsync` is not set to `always`, a Redis crash can lose unacknowledged messages. For billing-critical events, this is a risk that requires configuration attention (`appendonly yes` + `appendfsync always`) or a write-ahead log in the consumer.
- **Less ecosystem tooling.** Kafka has mature offset management, schema registry, Connectors, and third-party observability integrations. Redis Streams monitoring is less standardized (Latency, `STREAM INFO`, Redis Stack metrics).
- **Fan-out at scale.** WebSocket push at high scale requires Redis Pub/Sub or Streams fan-out. This works, but Redis is single-threaded for Pub/Sub fan-out — at extreme scale (>100K concurrent WebSocket connections), a separate channel layer is needed. This is not a concern at the current 85K MAU.

---

## Alternatives Considered

### Apache Kafka

**Rejected.**

Kafka's strengths — durable log-based retention, native exactly-once semantics (EOS) via Kafka Transactions, best-in-class fan-out, and a rich ecosystem — are real. However, they do not outweigh the constraints in this specific context:

| Criterion | Kafka | Redis Streams | Winner |
|---|---|---|---|
| Operational complexity | High: brokers, replication factor, partition assignment, KRaft/ZooKeeper | Low: managed Redis, same ops stack | Redis Streams |
| Team experience | Zero | All 6 engineers | Redis Streams |
| Setup time | 2+ weeks just to have a working cluster | 1–2 days | Redis Streams |
| Exactly-once (native) | Kafka Transactions (battle-tested) | Requires custom idempotency layer | Kafka |
| Throughput | 100K+/s | ~50–100K/s | Kafka (overkill here) |
| Message retention | Infinite (log-compacted topics) | Configurable via `MAXLEN` | Comparable |
| Consumer groups | Native, mature | `XREADGROUP`, mature | Kafka (richer tooling) |
| WebSocket integration | Requires HTTP proxy, separate consumer | Native via Redis Pub/Sub | Redis Streams |
| Managed cost | Confluent Cloud ≈ $500+/mo at this scale | Incremental Redis memory cost ≈ trivial | Redis Streams |

**Why Kafka is rejected:**

1. **No Kafka experience.** The team would spend the first week learning broker configuration, partition strategies, consumer group offset semantics, and producer acks — before writing a single notification. The 2-week constraint makes this untenable.
2. **Operational overhead.** A 3-replication Kafka cluster with ZooKeeper or KRaft requires dedicated monitoring, partition rebalancing, and regular maintenance. With no infrastructure engineer, this creates fragility.
3. **Cost.** Self-managed Kafka on EC2 requires at least 3 brokers for availability. Managed Confluent Cloud is priced for scale. Redis Streams runs on the existing instance.
4. **Over-engineering.** The system's real peak is ~500 req/s. Kafka is designed for hundreds of megabytes per second of throughput across thousands of topics. Redis Streams handles the current load with headroom to spare.

Kafka would be the right choice if the team had an infrastructure engineer, a 3-month timeline, and traffic in the millions of events per second. None of those conditions hold here.

---

## Summary

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| Operational complexity | Low | High |
| Team familiarity | High | None |
| Time to first value | 1–2 days | 2+ weeks |
| Throughput (current → target) | Sufficient (500 → 5,000/s) | Overkill |
| At-least-once delivery | Yes (via `XACK`) | Yes |
| Exactly-once (billing) | Custom idempotency required | Native (EOS) |
| WebSocket support | Native via Pub/Sub | Extra infrastructure |
| Infrastructure cost | Existing Redis | 3+ new brokers |
