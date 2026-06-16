# ADR-001: Notification Subsystem Architecture

## Status

**Proposed**

## Context

Our SaaS project management platform serves 85,000 monthly active users and handles ~2M tasks per month with a peak of ~500 requests/second. The current notification system runs synchronously inside the HTTP request cycle, causing:

- **Request timeouts**: Average latency of 800ms, spiking to 8s during peak hours
- **Silent failures**: Dropped notifications when email providers or webhook endpoints are unavailable
- **Cascading failures**: Two incidents where slow webhook endpoints caused connection pool exhaustion, taking down unrelated features
- **No delivery guarantees**: Billing-critical notifications (trial expired, payment failed) lack exactly-once semantics

We need to decouple notifications from the HTTP request cycle, support retry with exponential backoff, guarantee at-least-once delivery for billing events, and extend to WebSocket push notifications within two quarters. The system must handle 10x traffic growth without re-architecting.

**Constraints:**
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already runs in production for session storage and rate limiting
- No Kafka experience on the team
- 2-week maximum setup/migration window before delivering value
- Modest budget; Confluent Cloud at full scale is unaffordable
- Exactly-once semantics required for billing notifications

## Decision

**Choose Redis Streams.**

Redis Streams provides the right balance of capability, operational simplicity, and team fit for this use case. It meets our throughput requirements at 500 req/s with headroom to 10x, supports consumer groups with at-least-once delivery, and leverages our existing Redis investment.

The primary trade-off — achieving exactly-once semantics for billing notifications — is solved at the application layer via event idempotency keys, which is the standard pattern even in Kafka-based systems for billing-critical events.

## Consequences

### Benefits

- **Operational simplicity**: Redis is already running in production. No new system to operate, monitor, or debug under pressure. The team manages a single Redis instance that handles caching, sessions, and now streams.
- **Fast time-to-value**: A Python developer can implement a streams-based worker in hours. No topic configuration, no partition management, no ZooKeeper/KRaft. Estimated implementation: 3–5 days for the core pipeline vs. 2+ weeks for Kafka.
- **Sufficient throughput**: 500 req/s with 10x headroom is well within Redis Streams' capabilities. Redis Streams can handle tens of thousands of events per second on modest hardware.
- **Consumer groups and retry**: `XREADGROUP` provides at-least-once delivery with manual acknowledgment. Failed notifications can be requeued with exponential backoff using a dead-letter stream pattern.
- **Ordering guarantees**: Redis Streams maintains insertion order within a consumer group, ensuring task-update notifications are delivered in the correct sequence.
- **Message retention**: Configurable up to 512k entries per stream (and effectively unlimited with stream trimming). Sufficient for replay and debugging.
- **WebSocket extension**: Redis pub/sub integrates naturally with WebSocket push notifications planned for Q2, allowing a unified Redis-based real-time stack.
- **Cost**: No additional infrastructure cost. Self-hosting Redis Streams on existing hardware.

### Drawbacks

- **Exactly-once requires application logic**: Redis Streams provides at-least-once semantics only. Achieving exactly-once for billing notifications requires idempotency keys (e.g., storing processed event IDs in a Redis set with TTL). This is a known pattern but adds implementation complexity.
- **Not a durable log in the traditional sense**: Redis Streams is an in-memory structure with optional AOF persistence. A Redis crash with `appendfsync everysec` could lose up to 1 second of events. For billing-critical notifications, this risk must be evaluated — a hybrid approach (write to PostgreSQL first, then enqueue to Redis Streams) mitigates this.
- **Scaling ceiling**: At very high throughput (>50k events/sec sustained) or very large consumer groups (>100 consumers), Kafka's horizontal partitioning outperforms Redis Streams. Our 10x growth target of ~5,000 req/s remains within Redis Streams' comfortable range.
- **No native dead-letter queue**: Dead-letter handling requires a manual pattern (separate stream for failed messages, retry counter in the message body, or a sidekiq-style retry mechanism).

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for event streaming and would handle our use case with flying colors:

- **Throughput**: Orders of magnitude above our needs (millions of events/sec with proper partitioning)
- **Durability**: Persistent log with configurable retention (days to years). No data loss on restart.
- **Exactly-once semantics**: Native Kafka Transactions provide true exactly-once across producer, broker, and consumer — a stronger guarantee than Redis Streams' application-layer idempotency.
- **Mature ecosystem**: Dead-letter queues, schema registry, Kafka Connect, and stream processing (Kafka Streams/ksqlDB) are battle-tested.

**Why we rejected it:**

1. **Operational burden**: Self-managed Kafka on AWS requires ZooKeeper or KRaft, topic configuration, partition management, replica management, and cluster rebalancing. Without a dedicated infrastructure engineer, this creates significant operational risk.
2. **No team experience**: The learning curve is steep. The team would spend the first month reading documentation instead of delivering value. Misconfigurations (e.g., incorrect partition counts, acks settings) can cause subtle data loss or availability issues.
3. **Time to value**: A production-ready Kafka setup — including monitoring, alerting, and operational runbooks — typically takes a dedicated team 4–8 weeks. Our constraint is 2 weeks.
4. **Cost**: Even self-managed Kafka on EC2 requires at least 3 broker instances for high availability (recommended: 5), plus ZooKeeper nodes or KRaft quorum. At ~$0.10/hr per instance, that's $500+/month minimum, exceeding our modest budget.
5. **Over-engineering**: For 500 req/s with a 6-person team and a 2-week deadline, Kafka's capabilities far exceed our requirements. The operational complexity is not justified by the scale.

### PostgreSQL as Queue (rejected earlier)

Using PostgreSQL `LISTEN/NOTIFY` with a dedicated notifications table was considered:

- **Pros**: Zero new infrastructure, transactional consistency with the main DB, simple for the team to understand.
- **Cons**: No consumer groups, limited queue management, polling risk, and adds load to the primary database — the opposite of decoupling. Ruled out because the cascading failure risk (slow notifications affecting the DB) would persist.

## Summary

| Property | Redis Streams | Apache Kafka |
|----------|---------------|--------------|
| Throughput (500 req/s) | Exceeds requirement | Far exceeds requirement |
| Ordering guarantees | Per-stream ordering | Per-partition ordering |
| Message retention | Up to 512k entries (configurable) | Days to years |
| Consumer groups | Yes (`XREADGROUP`) | Yes ( mature) |
| Exactly-once semantics | Application-layer idempotency | Native Kafka Transactions |
| Operational complexity | Low (single binary, existing infra) | High (cluster management) |
| Team learning curve | Low (Redis experience exists) | High (no Kafka experience) |
| Time to production-ready | 1–2 weeks | 4–8 weeks |
| Infrastructure cost | Zero (leverages existing Redis) | $500+/month minimum |
| WebSocket integration | Native Redis pub/sub | Requires separate service |

**Recommendation: Redis Streams.** It delivers immediate value within the 2-week constraint, leverages existing infrastructure and team knowledge, and scales comfortably to our 10x growth target. Exactly-once semantics for billing events are implemented via idempotency keys — a standard pattern that the team can ship in the first iteration alongside the streams pipeline.