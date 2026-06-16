# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

### The Problem

The notification module currently executes synchronously inside the HTTP request cycle. As the platform has grown to 85,000 monthly active users and ~2 million tasks per month, this has caused:

- **Request timeouts**: Notification delivery (email, webhooks) blocks the HTTP response. Average latency is 800 ms; during peak hours it spikes to 8 seconds.
- **Silent failures**: When an email provider or webhook endpoint is unavailable, the notification is dropped with no retry and no dead-letter queue.
- **Cascading failures**: Two production incidents this year where a slow webhook endpoint exhausted the connection pool, taking down unrelated features across all web servers.
- **No delivery guarantees**: Billing-critical notifications (trial expiry, payment failure) require exactly-once delivery. The current system has no such guarantee.

### Scaling Requirements

We need to:
1. Decouple notifications from the HTTP request cycle (async processing)
2. Support retry with exponential backoff
3. Guarantee at-least-once delivery for billing events; exactly-once where feasible
4. Add real-time WebSocket push notifications within two quarters
5. Handle 10× traffic growth (500 → 5,000 req/s peak) without re-architecting

### Constraints

| Constraint | Implication |
|---|---|
| Team: 6 engineers (3 senior, 3 mid-level), no dedicated infra engineer | Cannot absorb high operational complexity |
| Redis already running in production (session storage, rate limiting) |边际 cost of using Redis Streams is near zero |
| No Kafka experience on the team | Kafka carries a significant learning curve |
| 2-week maximum setup/migration window | Must deliver value quickly, not perfect later |
| Modest budget | Cannot afford managed Confluent Cloud at scale |
| Exactly-once semantics required for billing notifications | Non-negotiable requirement |

### Traffic Profile

- Current peak: ~500 req/s
- Growth target: 10× → ~5,000 req/s
- At peak, a task update event may fan out to multiple notifications (email + webhook + WebSocket push)
- Estimated notification throughput at 10×: **~15,000–25,000 messages/second**

---

## Decision

**Use Redis Streams as the message broker for the notification subsystem.**

Redis Streams provides sufficient throughput for the current and 10×-scaled load, offers ordered delivery with consumer groups, requires no new infrastructure, and can be learned and operationalized within the 2-week constraint. It satisfies all hard requirements and avoids the operational burden that Kafka would impose on a 6-person team with no dedicated infrastructure engineer.

---

## Technical Comparison

### Throughput

| Broker | Typical Throughput | Notes |
|---|---|---|
| Redis Streams | 50,000–200,000 msg/s on commodity hardware | More than adequate for 25,000 msg/s target |
| Apache Kafka | 100,000–1,000,000+ msg/s | Massive headroom, but over-engineered for this scale |

At 25,000 messages/second (10× growth scenario), Redis Streams operates well within its comfortable range. Kafka's throughput advantage is irrelevant at this stage.

### Ordering Guarantees

Both brokers provide **ordered delivery within a partition/stream**.

- **Redis Streams**: Messages within a stream are consumed in order by a consumer group. Consumer groups (XREADGROUP) assign message ownership, ensuring one consumer processes each message.
- **Kafka**: Partitions guarantee ordering. A single partition with one consumer group gives total order; multiple partitions require key-based partitioning to preserve per-key order.

For notification fan-out (one task event → multiple notification types), **Redis Streams is sufficient**; Kafka's more sophisticated partitioning is not needed at this scale.

### Message Retention

| Broker | Retention Model |
|---|---|
| Redis Streams | Configurable via `MAXLEN` (~)` or `MINID`. Entries are removed when trimmed. No native compaction. |
| Apache Kafka | Time-and-size-based retention with log compaction. Supports retaining the full history of a key. |

Redis Streams' trimming model is adequate for notifications: we need at-least-once delivery, not the full event history that Kafka's log compaction provides. If message history is needed for replay, `XLEN` can be tuned to retain sufficient window.

### Consumer Groups

Both brokers support the consumer group pattern:

- **Redis**: `XREADGROUP` + `XACK` + pending entry list (PEL). If a consumer crashes, unacknowledged messages are re-delivered after `BLOCK` timeout.
- **Kafka**: Native consumer group offset management with `__consumer_offsets` topic. More mature offset tracking and rebalance strategies.

Redis Streams' consumer groups are sufficient for our retry semantics. Unacknowledged messages re-appear in the PEL after the consumer's `BLOCK` timeout, and a separate process can scan the PEL for stale entries to retry.

### Exactly-Once Semantics

This is the most important requirement for billing notifications.

- **Redis Streams**: Provides **at-least-once** delivery. Messages can be redelivered if a consumer fails before acknowledging. Achieving exactly-once requires **idempotency logic at the consumer layer** — for example, storing the processed message ID in a Redis set and checking it before sending.
- **Kafka**: Provides **at-least-once** by default. Exactly-once requires enabling `enable.idempotence=true` on the producer and using transactions with the consumer. Still requires idempotent consumer logic for full exactly-once guarantees.

**Neither broker provides native exactly-once delivery.** Both require idempotent consumer design. The difference is that Kafka's exactly-once is slightly more straightforward to implement (via producer idempotence + consumer transactions), but Redis's idempotency solution is equally viable for notification workloads and avoids the API complexity.

For billing notifications specifically: we will store the message ID in a deduplication set (e.g., a Redis key `notif:sent:{message_id}` with a TTL) before sending. The consumer checks this key before processing. This gives exactly-once semantics with Redis Streams.

### Operational Complexity

| Dimension | Redis Streams | Apache Kafka |
|---|---|---|
| Infrastructure | Zero new infra (Redis already running) | Requires new cluster (ZooKeeper/KRaft), monitoring, partition management |
| Setup time | 1–3 days | 1–2 weeks minimum for a team with no experience |
| Monitoring | Existing Redis monitoring stack | Must be built or integrated (Kafka exposes JMX, but dashboards are non-trivial) |
| Failure modes | Redis failure affects sessions + notifications (mitigated by Redis HA/sentinel) | Kafka failure is isolated but harder to diagnose without expertise |
| Scaling | Vertical scaling + Redis Cluster for sharding | Horizontal scaling via partition reallocation (complex, requires care) |
| Team learning curve | Low (team already knows Redis) | High (no prior Kafka experience) |

The 2-week constraint is the decisive factor. Redis Streams can be integrated in days. Kafka, even with a managed offering, requires cluster design decisions (partition count, replication factor, consumer group strategy) that a Kafka-novice team cannot make safely in two weeks.

---

## Consequences

### Benefits of Redis Streams

1. **No new infrastructure**: Redis is already running for sessions and rate limiting. Redis Streams uses the same Redis instance with no additional operational surface.
2. **Fast implementation**: A 6-person team with Redis familiarity can implement the full notification pipeline (producer → stream → consumer with retry) in 1–2 weeks.
3. **Sufficient throughput**: 50,000–200,000 msg/s comfortably exceeds the 25,000 msg/s needed at 10× growth.
4. **Ordered delivery with consumer groups**: `XREADGROUP` ensures one consumer processes each message; `XACK` and the pending entry list handle retries cleanly.
5. **Exactly-once for billing notifications**: Idempotency via a deduplication key (`notif:sent:{message_id}`) is straightforward to implement and covers the billing use case.
6. **Existing Redis expertise**: No new learning curve for the core data store. The team extends existing knowledge rather than adopting a foreign system.
7. **Supports WebSocket push**: A future WebSocket worker can subscribe to the same Redis Streams channel, enabling real-time push without a separate message bus.
8. **Low operational overhead**: Redis Streams requires no new monitoring dashboards, no partition rebalancing, no JVM tuning.

### Drawbacks and Risks

1. **Throughput ceiling**: At very high scale (100,000+ msg/s sustained), Redis Streams would require sharding via Redis Cluster. This adds complexity and a migration step. However, this ceiling is ~4× above our 10× growth target.
2. **No native log compaction**: If we need to replay the full event history (e.g., for a new notification type that consumes historical events), Kafka's log compaction is superior. Redis Streams can retain a configurable window, but not an unbounded history.
3. **Operational coupling**: If the Redis instance suffers an outage, both sessions/rate-limiting and notifications are affected. Mitigation: enable Redis Sentinel or Redis Cluster for HA. This is an existing infrastructure item that should be addressed regardless of this ADR.
4. **At-least-once requires careful consumer design**: The consumer must implement idempotency checks. If developers forget to check the deduplication key, duplicate notifications will be sent. This is mitigated by a shared library with a decorator or base class for consumer message handlers.
5. **No native backpressure**: Redis Streams consumers pull messages via `XREADGROUP`. If a consumer is overwhelmed, it simply does not acknowledge messages fast enough, and the PEL grows. A monitoring alert on PEL size is required.
6. **Maturity**: Redis Streams (introduced in Redis 5.0) is less mature than Kafka. Consumer group semantics and the PEL model have some edge cases around block timeouts and rebalance that require careful testing.

### Mitigation Plan

| Risk | Mitigation |
|---|---|
| Redis HA coupling | Deploy Redis Sentinel; already a best practice for the existing Redis use case |
| Duplicate notifications | Shared consumer library with mandatory idempotency check decorator |
| PEL growth / consumer lag | Alert on `XPENDING` count exceeding threshold |
| Scale ceiling | Design stream consumer groups to be horizontally scalable from the start; document the Redis Cluster migration trigger point |
| Consumer group edge cases | Write integration tests covering consumer crash, restart, and network partition scenarios |

---

## Alternatives Considered

### Apache Kafka

**Why it was considered**: Kafka is the industry standard for event streaming at scale. It offers superior throughput (1M+ msg/s), log compaction, proven exactly-once semantics via transactions, and a rich ecosystem (Kafka Connect, Schema Registry, ksqlDB). It is the de facto choice for high-scale event-driven architectures.

**Why it was rejected**:

1. **No Kafka experience**: The team has zero production Kafka experience. Designing partition strategies, consumer group offsets, and replication factors without expertise invites production incidents.
2. **Infrastructure burden**: Kafka requires a cluster ( ZooKeeper or KRaft in newer versions), monitoring, partition leadership balancing, and log retention management. A 6-person team with no dedicated infrastructure engineer cannot sustain this.
3. **2-week constraint violated**: Even with a managed offering (e.g., AWS MSK, Confluent Cloud at entry tier), the team would spend the full 2 weeks on cluster setup and learning — not on delivering notification value.
4. **Over-engineered for current scale**: The platform's 500 req/s peak will grow to ~5,000 req/s at 10×. Kafka is designed for tens of thousands to millions of messages per second. The throughput gap is 20–200× above our needs.
5. **Exactly-once is not free in Kafka either**: While Kafka's `enable.idempotence` + transactions simplifies exactly-once, it still requires careful consumer implementation. The advantage over Redis idempotency is marginal for this use case.

**Kafka is the right choice if**: The platform grows to 50,000+ msg/s sustained, the team expands to include a dedicated platform/infrastructure engineer, or the notification system evolves into a general-purpose event backbone for multiple microservices. Re-evaluate at that stage.

### Other Options Not Considered in Detail

- **Amazon SQS/SNS**: Fully managed, but queues are pull-based (SNS is push-based but fan-out to many consumers is complex). No ordering guarantee across queues. Higher operational cost at scale.
- **RabbitMQ**: Mature but designed for task queues, not event streaming. Routing complexity grows with notification type count.
- **Database-backed queues (PostgreSQL LISTEN/NOTIFY or a jobs table)**: Would work but lacks consumer group semantics, retry management, and dead-letter handling built into Redis Streams.

---

## Recommendation Summary

**Redis Streams is the correct choice for this team and this stage of growth.** The notification requirements (async decoupling, retry with backoff, at-least-once/exactly-once for billing) are fully met. The 10× growth target is well within Redis Streams' comfortable throughput range. The existing Redis infrastructure means zero new operational surface. The team can deliver the notification subsystem within the 2-week window.

Kafka is the right long-term choice as the system scales toward 50,000+ msg/s or as the architecture evolves toward a microservice event backbone — but that decision should be made when the scale materializes and the team has grown.

---

*Document version: 1.0*
*Decision owner: Engineering Team*
*Review date: When throughput exceeds 50,000 msg/s sustained, or when notification event types exceed 20 distinct types*