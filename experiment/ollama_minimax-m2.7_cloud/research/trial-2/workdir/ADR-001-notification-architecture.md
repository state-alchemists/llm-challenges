# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

The notification module currently sends emails and webhooks synchronously inside the HTTP request cycle. This causes request timeouts (avg 800ms, spikes to 8s), silent failures with no retry, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical events.

**Scaling target:**
- Decouple notifications from the HTTP request cycle
- Retry with exponential backoff
- At-least-once delivery for all events; exactly-once for billing events
- WebSocket push notifications within 2 quarters
- Handle 10x traffic growth (from ~500 req/s peak today)

**Constraints:**
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already running in production for session storage and rate limiting
- No Kafka experience on the team
- 2-week maximum setup/migration before delivering value
- Modest budget — Confluent Cloud at full scale is unaffordable
- Exactly-once semantics required for billing notifications (trial expired, payment failed)

**Current load estimate:**
- ~2M tasks/month → roughly 2–4M notification events/month at current notification rate
- Peak: ~500 req/s, but notification volume is bursty (e.g., mass task assignments, bulk completions)
- 10x growth target means planning for ~5,000 req/s peak

---

## Decision

**Choose Redis Streams.**

Redis Streams is the right fit for this team and problem. The existing Redis investment eliminates new infrastructure, the team can ship a working system within days rather than weeks, and Redis Streams provides sufficient throughput, consumer groups with acknowledgment, and the building blocks for at-least-once delivery. Exactly-once for billing events is achieved application-layer via deduplication tables.

---

## Consequences

### Pros of Redis Streams

| Property | Detail |
|---|---|
| **Operational simplicity** | Redis is already in production. No new servers, no ZooKeeper/KRaft, no partition planning. The team manages one fewer system. |
| **Fast time-to-value** | A proof-of-concept worker can be running in 1–2 days. Full migration within the 2-week constraint is realistic. |
| **Throughput** | Redis Streams handles 50,000–100,000 ops/sec on a modest instance — far above the current ~500 req/s peak and sufficient headroom for 10x growth. |
| **Consumer groups (XREADGROUP)** | Native support for multiple concurrent consumers in a consumer group, with per-message acknowledgment (XACK). Enables load balancing and parallel processing of notification types (email, webhook, WebSocket). |
| **Retry semantics** | Failed messages can be re-read from the stream after a timeout (XPENDING + XCLAIM). Pair with a dead-letter stream for exhausted retries. |
| **Ordering** | XREADGROUP preserves insertion order within a consumer group. For a single logical notification stream this is sufficient. |
| **Existing Go client compatibility** | Popular Redis Go clients (go-redis/redis, go-redis) support Streams natively. |
| **Cost** | No additional managed service cost. Self-managed on existing Redis instance (or upgrade Redis instance size if needed). |

### Cons of Redis Streams

| Property | Concern | Mitigation |
|---|---|---|
| **Message retention** | Streams are memory-bounded. Without a max-length policy, unbounded growth can exhaust memory. | Set `MAXLEN ~` or `MINID` trimming on write. Treat stream as a buffer, not a permanent log. |
| **Exactly-once semantics** | Redis Streams guarantees at-least-once (XACK + re-reading unacknowledged messages). True exactly-once requires application-layer work. | Use a `processed_event_ids` table in PostgreSQL (idempotency key per event). On consumer startup, skip events already in the dedup table. |
| **No native dead-letter queue** | Messages that exceed retry limits need manual handling. | Implement a DLQ pattern: on exhaustion, XADD to a `notifications.dlq` stream with retry metadata. Monitor DLQ size and alert. |
| **Horizontal scaling ceiling** | A single Redis instance is the bottleneck. Throughput is bounded by Redis CPU and network. | Redis Cluster supports sharding streams by key, but this adds complexity. At 10x scale (5,000 req/s), a well-tuned single Redis instance is likely still sufficient; sharding can be introduced later if needed. |
| **Visibility/debugging** | Stream offsets, pending message counts, and consumer lag require explicit monitoring tooling. | Expose metrics: stream length, pending count per consumer group, consumer group lag, DLQ depth. Use Redis INFO and consumer-reported metrics. |

---

## Alternatives Considered

### Apache Kafka

| Property | Kafka vs. Redis Streams |
|---|---|
| **Operational complexity** | Kafka requires ZooKeeper or KRaft for metadata, broker configuration, partition assignment, replication factor tuning, and consumer group offset management. On a 6-person team with no dedicated infra engineer, this is significant overhead. |
| **Setup time** | Even with a managed offering (MSK, Confluent Cloud), the team needs 1–2 weeks to learn producer/consumer patterns, configuration, and monitoring. This violates the 2-week constraint. |
| **Exactly-once semantics** | Kafka provides exactly-once semantics via its transactions API (idempotent producers + consumer offset commits). This is more robust than Redis Streams' application-layer dedup. However, it requires careful configuration and adds complexity. |
| **Throughput** | Kafka handles millions of events/second — far above what this system needs. It is over-engineered for the current and 10x-scaled load. |
| **Message retention** | Kafka retains messages on disk for configurable periods (hours, days, weeks). Useful for audit trails and replay. Redis Streams' memory-bounded retention is a limitation if long-term replay is needed later. |
| **Ecosystem** | Kafka Connect, Kafka Streams, schema registry — powerful primitives for future event-driven work (e.g., audit log, data pipeline). These are not needed today but could accelerate the WebSocket notification feature in 2 quarters. |
| **Cost** | Managed Kafka (MSK) at production scale starts at ~$0.10/hr per broker + storage. At 3 brokers + replication, this is $200–500/month minimum. Redis is already paid for. |

**Why Kafka was rejected:**

Kafka is the correct choice for teams that (a) already run Kafka, (b) have infrastructure or platform engineering support, or (c) need the throughput and ecosystem for broader event-driven architecture. None of those conditions apply here. The 2-week constraint and team composition make Kafka's operational overhead a liability, not an asset. The billing-critical exactly-once requirement can be met adequately via application-layer deduplication with Redis Streams, which is simpler than it sounds and is a well-understood pattern.

---

## Summary

| Criterion | Redis Streams | Apache Kafka |
|---|---|---|
| Operational overhead | Low (existing infra) | High (new cluster, brokers, ZooKeeper/KRaft) |
| Time to first value | 1–2 days | 1–2 weeks |
| Team fit (6 eng, no infra) | Strong | Weak |
| Throughput | Sufficient (50k–100k ops/sec) | Excessive (millions/sec) |
| Exactly-once (billing) | Application-layer dedup | Native (transactions API) |
| Retention | Memory-bounded, short-term | Disk-backed, long-term |
| 10x scale path | Redis Cluster (future) | Native (already scales) |
| Budget impact | Near zero | $200–500/month managed |

**Recommendation: Redis Streams.** Ship a working notification worker within 2 weeks, use a PostgreSQL idempotency table for billing deduplication, and revisit Kafka if the WebSocket push feature or event-driven expansion in 2+ quarters demands it.
