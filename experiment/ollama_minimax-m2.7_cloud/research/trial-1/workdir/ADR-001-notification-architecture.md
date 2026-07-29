# ADR-001: Notification Subsystem Message Broker Selection

**Status:** Proposed

---

## Context

Our SaaS project management platform currently handles notifications synchronously inside the HTTP request cycle, causing request timeouts (avg 800ms, spikes to 8s), silent failures, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical events.

We need to decouple notification processing from the request cycle with:
- Async processing with retry and exponential backoff
- At-least-once delivery for billing events, exactly-once where feasible
- Support for 10x traffic growth (from ~500 req/s peak to ~5,000 req/s)
- WebSocket push notification capability within 2 quarters
- No more than 2 weeks of setup/migration before delivering value

**Team constraints:** 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer, no Kafka experience, but strong Redis experience since Redis is already in production for session storage and rate limiting.

**Budget:** Modest — cannot afford managed Confluent Cloud at full scale.

---

## Decision

**Choose Redis Streams.**

Rationale: Redis Streams provides sufficient throughput for our current and projected load, requires zero new infrastructure (we already run Redis), has a shallow learning curve for the team, and can be implemented within the 2-week constraint. Kafka's operational complexity, infrastructure requirements, and learning curve make it a poor fit for our team size and timeline.

---

## Consequences

### Pros of Redis Streams

| Property | Detail |
|---|---|
| **Operational simplicity** | Redis is already running. No new infrastructure, no new ports, no new services to monitor. |
| **Team familiarity** | The team has production Redis experience. No learning curve for the transport layer. |
| **Throughput adequate** | Redis Streams handles 50,000+ ops/sec on modest hardware — well above our 5,000 req/s target. |
| **Consumer groups** | XREADGROUP provides partitioned consumption with ACK-based offset tracking, giving at-least-once delivery. |
| **Message retention** | Configurable retention (up to billions of entries with `MAXLEN ~`), sufficient for our retry window needs. |
| **Exactly-once via idempotency** | Billing notifications can use deduplication keys stored in Redis (or PostgreSQL) to achieve exactly-once semantics. |
| **XADD + XACK semantics** | Unacknowledged messages remain in the stream and are redelivered on consumer restart — natural retry mechanism. |
| **Dead-letter handling** | Failed messages (after N retries) can be moved to a dedicated `notifications.dlq` stream. |
| **WebSocket readiness** | Redis Pub/Sub or Streams with client-side polling maps directly onto WebSocket notification delivery. |
| **Setup time** | 1–2 days to add the stream producer, consumer group, and worker process. Full migration in under 2 weeks. |

### Cons of Redis Streams

| Concern | Mitigation |
|---|---|
| **Not a durable log in the same class as Kafka** | Redis Streams persists to RDB+AOF; configure `appendfsync always` for durability at minor throughput cost, or accept at-least-once with async persistence. |
| **No native exactly-once consumption** | Requires application-level deduplication (store message ID or payload hash in a Redis set or PostgreSQL table with TTL). This is straightforward and the team already understands Redis. |
| **Single-stream throughput ceiling** | At extreme scale (>100K req/s), a single stream could become a bottleneck. At 5,000 req/s projected, this is not a concern. |
| **No native compaction/retention policies per consumer group** | Must manage `MAXLEN` or `MINID` manually via `XTRIM` or `XADD MAXLEN ~`. A cron job every minute is sufficient. |
| **No Kafka-style stream processing** | If complex fan-out or stateful stream joins are needed in the future, Redis Streams lacks Kafka Streams' capabilities. |
| **Ordered within a stream, not global** | Message ordering is guaranteed per stream, not across multiple streams. For billing notifications that require a single total order, use a single stream keyed by `billing:{user_id}`. |

---

## Alternatives Considered

### Apache Kafka

| Property | Kafka Reality |
|---|---|
| **Operational complexity** | Requires ZooKeeper or KRaft (3+ brokers for HA), partition management, replication factor configuration, topic retention policies, consumer group offset management. No dedicated infra engineer. |
| **Infrastructure cost** | Minimum 3 brokers for HA; self-managed on EC2 or EKS adds significant operational burden and cost versus our existing Redis. |
| **Learning curve** | Kafka is a different paradigm (partitioned log as first-class abstraction). The team has no production experience. Debugging consumer lag, offset committed, under-replicated partitions requires deep knowledge. |
| **Setup time** | A production-ready Kafka cluster with TLS, auth, monitoring, and alerting takes 1–2 weeks alone — before any consumer code is written. |
| **Throughput** | Kafka excels at >100K msg/s with strong ordering guarantees across partitions. Our peak is 5,000 req/s projected — well within Redis Streams' range. |
| **Exactly-once** | Kafka's exactly-once semantics (transactions API) is complex to implement correctly and adds overhead. Idempotent producers + consumer deduplication is equivalent for billing use cases. |
| **WebSocket integration** | Requires a separate service (Kafka WebSocket proxy) to bridge Kafka consumers to WebSocket clients — additional moving parts. |
| **Verdict** | Kafka is the right tool at >50,000 req/s, multi-datacenter requirements, or when a dedicated platform/infrastructure team exists. Our constraints make it a 3–6 month investment just to reach parity with what Redis Streams gives us in 2 weeks. |

---

## Recommendation Summary

Redis Streams satisfies all stated requirements within the team's capability and time constraint:

- **Throughput:** 5,000 req/s projected ≤ Redis Streams capacity
- **Delivery guarantees:** Consumer groups + ACK + application-level deduplication = exactly-once for billing
- **Retry/DLQ:** XACK for retry, XADD to `notifications.dlq` for dead-letter
- **Operational risk:** Zero new infrastructure; Redis is already monitored and understood
- **Migration time:** Under 2 weeks to production value
- **Future WebSocket path:** Direct mapping via Redis Pub/Sub or Streams polling

Kafka is rejected not because it is technically inferior at scale — it is not needed at our scale, and its operational overhead would consume the entire team's infrastructure capacity for months.
