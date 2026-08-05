# ADR-001 — Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-08-05
- **Deciders**: Engineering team (6 engineers)
- **Context tags**: notifications, messaging, scaling, reliability

## Context

Our SaaS project management platform (85,000 MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails and webhooks for task updates, assignments, completions, and billing events — synchronously inside the HTTP request cycle. This has caused four documented problems:

1. **Request timeouts**: Notification sending blocks responses (avg 800ms, spiking to 8s at peak).
2. **Silent failures**: Downstream provider outages drop notifications with no retry or dead-letter queue.
3. **Cascading failures**: Two incidents this year where slow webhook endpoints exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

We must decouple notification from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing where feasible), add real-time WebSocket push within 2 quarters, and absorb 10x traffic growth (~5,000 req/s peak) without re-architecting.

**Constraints:**

- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- No Apache Kafka experience on the team.
- Redis already running in production (session storage, rate limiting).
- Migration/setup must deliver value within 2 weeks.
- Modest budget — managed Confluent Cloud at scale is not affordable today.
- Exactly-once semantics must be maintained for billing notifications.

## Decision

We will use **Redis Streams** as the notification subsystem's message broker.

Redis Streams (available since Redis 5.0) provides ordered, append-only logs with consumer group support (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`), which satisfies the core decoupling and delivery requirements. Because we already operate Redis in production and the team is familiar with it, the setup time fits the 2-week constraint: we add a dedicated Redis instance for streams (isolated from the session cache to avoid resource contention) and implement consumers in our existing Flask workers.

Exactly-once delivery for billing notifications will be achieved through **idempotent consumers**: each billing notification handler writes a deduplication record to PostgreSQL before processing, using the Redis stream message ID as the idempotency key. If a message is delivered twice (which Redis Streams permits under at-least-once semantics), the second delivery finds the existing record and skips processing. This is the same pattern used by systems like Sidekiq Pro and AWS SQS + DynamoDB, and it meets the billing requirement without requiring a transactional message broker.

## Consequences

### Positive

- **Fast time to value**: Redis is already in our stack. The team can prototype consumer groups and retry logic within days, not weeks. No new operational domain to learn.
- **Sufficient throughput**: A single Redis instance handles hundreds of thousands of messages per second — well above our 10x growth target of ~5,000 req/s peak. No sharding or clustering required at this scale.
- **Low operational cost**: One additional Redis instance (or a dedicated node on the existing cluster) versus a 3+ broker Kafka cluster plus monitoring, balancing, and partition management. Modest budget constraint satisfied.
- **Ordered delivery per stream**: Redis Streams guarantee insertion order within a stream. Partitioning billing events into a dedicated stream preserves ordering for that domain.
- **Consumer groups with pending-entry lists**: `XPENDING` and `XCLAIM` give us built-in visibility into in-flight and stale messages, enabling retry with exponential backoff and dead-letter routing without custom bookkeeping.
- **No new operational skill gap**: The team already troubleshoots Redis. Kafka would require learning broker administration, partition rebalancing, lag monitoring, and KRaft/ZooKeeper management with no one to mentor.

### Negative

- **No native exactly-once semantics**: Redis Streams provide at-least-once delivery. Exactly-once for billing requires the idempotent-consumer pattern described above, which adds a PostgreSQL write per billing notification. This is correct but introduces a coupling point: the consumer must be online to deduplicate. If the deduplication table is unavailable, the consumer must NACK and retry rather than skip.
- **Message retention is bounded by memory/disk**: Unlike Kafka's configurable long-term retention to external storage, Redis Streams hold messages in memory (with optional AOF/RDB persistence). For our notification workload (short-lived, high-throughput, processed within seconds to minutes), this is acceptable — we will set `MAXLEN` to cap stream length and `XTRIM` aggressively after acknowledgment. But if a future use case requires replaying months of historical messages, Redis Streams would need supplementary archival.
- **Single-node availability**: A standalone Redis instance is a SPOF unless we configure Redis Sentinel or Redis Cluster. We should plan for Sentinel on the notification Redis instance before the WebSocket push feature ships (quarter 2).
- **Consumer group scaling ceiling**: Redis Streams consumer groups do not support dynamic partition splitting. If throughput grows beyond what a single stream can handle, we would need to manually shard into multiple streams and route producers. This is acceptable at 10x growth (~5,000 req/s) but would need re-evaluation at ~50x.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event streaming platform with native support for partitioned topics, long-term message retention, consumer groups with offset management, and exactly-once semantics via idempotent producers and transactional consumers (KIP-447).

We rejected Kafka for this decision because:

- **Operational complexity exceeds team capacity**: A minimal production Kafka deployment requires 3 brokers (for replication), plus monitoring (lag, under-replicated partitions, rebalances), and either KRaft or ZooKeeper. Our 6-person team has no Kafka experience and no dedicated infrastructure engineer. Operating Kafka correctly under failure scenarios (broker loss, partition leader election, consumer rebalances) requires expertise we do not have on staff.
- **Setup time violates the 2-week constraint**: Even with managed Confluent Cloud (which the budget does not support at scale), integrating Kafka into the Flask monolith, standing up producers and consumers, testing exactly-once transaction flows, and building operational runbooks would take 3–5 weeks minimum. Self-hosted adds another 1–2 weeks.
- **Budget**: Managed Confluent Cloud at our current and projected throughput costs significantly more than a dedicated Redis instance. A self-hosted Kafka cluster requires 3+ EC2 instances, EBS volumes, and monitoring infrastructure.
- **Throughput is overkill**: Kafka's design sweet spot (millions of messages/sec, multi-TB retention, multi-consumer topology) is well beyond our 10x growth target. We would pay operational complexity for capacity we do not need.

We would revisit Kafka if: (a) the team grows a dedicated infrastructure function, (b) throughput exceeds ~50,000 req/s requiring multi-consumer-topology fan-out, or (c) we need long-term event replay (months of retained messages for audit or analytics).

### RabbitMQ

RabbitMQ was also considered briefly. It offers mature routing, dead-letter exchanges, and message-level acknowledgment. However, it introduces a new operational component (no team experience, no existing deployment), its routing model is queue-centric rather than log-centric (making replay harder), and it does not provide native exactly-once semantics either. Redis Streams won on operational simplicity and the existing-investment argument.