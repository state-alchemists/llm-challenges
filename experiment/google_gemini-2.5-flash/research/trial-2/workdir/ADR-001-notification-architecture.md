# ADR-001: Notification Subsystem Architecture Decision

## Status
Proposed

## Context
The existing SaaS project management platform (85,000 MAU, ~2M tasks/month, peak ~500 req/s) suffers from critical issues in its synchronous notification module:
1.  **Request timeouts**: Notifications block HTTP responses, leading to high latency (800ms avg, 8s peak).
2.  **Silent failures**: No retries or dead-letter queue for email/webhook failures.
3.  **Cascading failures**: Slow webhook endpoints caused connection pool exhaustion.
4.  **No delivery guarantees**: Billing-critical notifications lack exactly-once delivery.

The new notification subsystem must:
*   Decouple notifications from the HTTP request cycle.
*   Support retry with exponential backoff.
*   Guarantee at-least-once delivery, with exactly-once for billing events.
*   Support real-time WebSocket push notifications within 2 quarters.
*   Handle 10x traffic growth without re-architecture.

**Constraints:**
*   Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
*   Existing Redis deployment for session and rate limiting.
*   No Kafka experience on the team.
*   Max 2 weeks setup/migration for initial value delivery.
*   Modest budget (no full-scale Confluent Cloud).

## Decision
**Redis Streams** will be used for the notification subsystem.

This decision prioritizes leveraging existing team knowledge and infrastructure, rapid initial deployment, and simpler operational overhead, while still meeting the critical scaling and delivery guarantees. Redis Streams provides the necessary features for asynchronous processing, message retention, consumer groups, and at-least-once delivery, and can be extended for exactly-once semantics for critical messages. Its integration with the existing Redis setup minimizes the learning curve and operational burden on a small team without dedicated infrastructure expertise.

## Consequences
**Pros:**
*   **Leverages existing infrastructure and expertise**: Reduces setup time and operational complexity, as Redis is already deployed and understood by the team.
*   **Faster time to value**: Minimal setup/migration work (within the 2-week constraint).
*   **Simplified operations**: Redis is generally simpler to operate than Kafka, requiring less specialized knowledge for monitoring, scaling, and maintenance.
*   **At-least-once delivery**: Native support for message acknowledgments within consumer groups ensures messages are processed.
*   **Message retention**: Configurable message retention allows for replaying messages if needed.
*   **Consumer Groups**: Provides scalable message consumption across multiple consumers.
*   **Exactly-once semantics (feasible)**: Can be achieved for critical billing notifications by combining consumer groups with idempotent processing on the consumer side, and transaction logs if using Redis with AOF persistence.
*   **Real-time capabilities**: Redis Pub/Sub (or Streams directly) is well-suited for WebSocket push notifications.
*   **Modest budget**: Open-source Redis is free, and self-hosting is manageable with existing infrastructure.

**Cons:**
*   **Scalability ceiling**: While capable of 10x growth, Redis Streams may hit a scalability ceiling earlier than Kafka for extreme throughput (100x+ growth or very high data volume per message) due to its single-threaded nature per instance and reliance on a single primary for writes. Vertical scaling limits might eventually be reached, requiring sharding, which adds complexity.
*   **Disk persistence**: While Redis has persistence (RDB/AOF), it is not designed as a distributed log storage system like Kafka. Very long-term, immutable log retention (years) is more natural for Kafka.
*   **Feature set**: Redis Streams has a more focused feature set compared to Kafka's broader ecosystem of connectors, stream processing frameworks (Kafka Streams, ksqlDB), and enterprise tooling. This might require more custom development for advanced use cases.
*   **Observability**: Out-of-the-box monitoring and tooling for Redis Streams are good but not as mature or extensive as the Kafka ecosystem.

## Alternatives Considered
**Apache Kafka** was considered but rejected due to the following reasons:
*   **High operational complexity**: Kafka is a distributed system known for its complexity in setup, configuration, monitoring, and scaling. This would place a significant burden on a small engineering team (6 people, no dedicated infrastructure engineer) with no prior Kafka experience. The learning curve alone would exceed the 2-week initial value delivery constraint.
*   **Resource intensive**: Self-hosting Kafka requires significant compute, memory, and disk resources, which might conflict with the "modest budget" constraint if managed services like Confluent Cloud are too expensive at scale.
*   **Time to value**: The initial setup, configuration, and integration of Kafka would likely take longer than 2 weeks, delaying the immediate benefits of asynchronous notifications.
*   **Overkill for initial needs**: While Kafka offers superior throughput and long-term message retention for extremely high-volume, global-scale systems, Redis Streams can comfortably handle the current and projected 10x scaling target of 5,000 req/s. The full power and complexity of Kafka are not immediately necessary.
*   **Exactly-once semantics**: While Kafka provides strong exactly-once semantics with its producer and consumer APIs, implementing and operating it correctly to achieve this on a new system with an inexperienced team would be challenging. Redis Streams, combined with idempotent consumers, can achieve the necessary guarantees with less operational overhead for billing-critical events.