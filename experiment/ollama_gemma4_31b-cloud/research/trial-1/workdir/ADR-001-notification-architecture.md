# ADR 001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system operates synchronously within the HTTP request cycle, leading to request timeouts (spikes up to 8s), silent failures of external webhooks/email providers, and cascading failures that exhaust connection pools. 

Key constraints and requirements:
- **Team**: 6 engineers, no dedicated infra engineer.
- **Infrastructure**: Already running Redis in production; no Kafka experience.
- **Reliability**: Must guarantee at-least-once delivery for general events and exactly-once semantics for billing-critical notifications.
- **Scale**: Currently 500 req/s peak; must support 10x growth (5,000 req/s) without re-architecting.
- **Timeline**: Setup/migration must be completed within 2 weeks to deliver value.
- **Budget**: Modest; managed Kafka (Confluent) is currently cost-prohibitive.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives for an asynchronous event-driven architecture while minimizing operational overhead.

1. **Operational Simplicity**: The team already manages Redis. Adding Streams requires no new infrastructure, no new monitoring stacks, and no learning curve for a complex distributed log like Kafka. This ensures we meet the 2-week delivery window.
2. **Throughput and Latency**: With a peak of 500 req/s (and a 10x target of 5,000 req/s), Redis Streams easily handles the load. Being in-memory, it provides significantly lower producer latency than Kafka, resolving the current request timeout issue.
3. **Consumer Groups**: Redis Streams supports Consumer Groups, enabling the scaling of worker processes to handle retries and exponential backoff across multiple consumers.
4. **Message Retention**: While Kafka's disk-based retention is superior, Redis's `XADD` with `MAXLEN` (approximate capping) is sufficient for notifications, where messages are typically processed quickly and don't require long-term archival in the stream itself.
5. **Delivery Guarantees**:
    - **At-least-once**: Achieved via the `XACK` (acknowledgment) mechanism. Messages not acknowledged are reclaimed via `XPENDING` and `XCLAIM`.
    - **Exactly-once (Billing)**: Since Redis Streams provides at-least-once delivery, we will implement **idempotency** at the consumer level. By storing a `notification_id` in PostgreSQL (which is already our source of truth), we ensure that billing events are processed exactly once regardless of stream redeliveries.

## Consequences
### Pros
- **Zero New Infrastructure**: Leverages existing Redis deployment.
- **Low Latency**: Immediate decoupling of HTTP requests from notification delivery.
- **Rapid Implementation**: The team can implement the producer/consumer pattern in days, not weeks.
- **Scale**: Sufficient head-room to handle 5,000 req/s comfortably.

### Cons
- **Memory Pressure**: As an in-memory store, large backlogs of unconsumed messages could impact Redis memory usage. We will mitigate this using `MAXLEN` to cap stream size.
- **Persistence Trade-off**: While Redis has AOF/RDB, it is not as durable as Kafka's distributed disk log. However, for notifications, the risk is acceptable given that the source of truth remains in PostgreSQL.

## Alternatives Considered
### Apache Kafka
Kafka was rejected due to the following:
- **Operational Complexity**: Kafka requires Zookeeper (or KRaft) and significant tuning for stability. Without a dedicated infra engineer, the operational burden on a 6-person team is too high.
- **Learning Curve**: The team has zero Kafka experience; the time spent learning "partitions," "offsets," and "consumer rebalancing" would violate the 2-week delivery constraint.
- **Cost**: Managed Kafka services exceed the current budget, and self-hosting would increase the "operational tax" on the engineering team.
- **Overkill**: Kafka's strengths (massive throughput, long-term retention) are not required for a 5,000 req/s notification system.
