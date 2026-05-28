---
Title: ADR-001 Notification Subsystem Architecture
Status: Proposed
---

# ADR-001 Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification module, part of a Python/Flask monolith, handles email and webhook dispatch synchronously within the HTTP request cycle. This has led to critical issues including request timeouts (up to 8s during peak), silent failures due to lack of retry mechanisms, cascading failures from slow webhook endpoints, and a complete absence of delivery guarantees for billing-critical notifications.

The system needs to evolve to support asynchronous processing, retry with exponential backoff, guarantee at-least-once delivery for all notifications, achieve exactly-once delivery for billing-critical events, and facilitate future real-time WebSocket push notifications. The solution must scale to 10x current traffic (up to 5000 req/s equivalent).

Key constraints:
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure engineer.
- **Existing Technology**: Redis is already in production for session management and rate limiting.
- **Expertise Gap**: No current team experience with Apache Kafka.
- **Time-to-Value**: Initial setup and migration to deliver value must be completed within 2 weeks.
- **Budget**: Modest, ruling out expensive managed Kafka services at full scale.
- **Delivery Guarantees**: Exactly-once semantics are mandatory for billing notifications.

## Decision
We choose **Redis Streams** as the foundation for the new asynchronous notification subsystem.

This decision is driven primarily by the critical constraints around team expertise, operational overhead, and time-to-value. Redis Streams provides a robust, battle-tested messaging primitive that can be quickly integrated and operated by a team already familiar with Redis.

## Consequences

### Positive
- **Reduced Operational Overhead**: Leverages existing Redis infrastructure and team expertise, minimizing the learning curve and operational burden. No new complex distributed system to manage from scratch.
- **Fast Time-to-Value**: Integration is straightforward, allowing the team to deliver async notifications, retries, and basic delivery guarantees within the 2-week time constraint.
- **Effective Decoupling**: Offloads notification sending from the main request path, eliminating timeouts and cascading failures.
- **At-Least-Once Delivery**: Redis Streams with consumer groups and `XACK` inherently supports at-least-once processing, which can be extended to exactly-once for billing events with idempotent consumers.
- **Exactly-Once Semantics**: Achievable by carefully managing consumer state and using idempotent consumers, aligning with the critical billing notification requirement.
- **Real-time Capabilities**: Redis Streams and Pub/Sub are well-suited for backing future WebSocket push notifications, requiring minimal additional infrastructure.
- **Cost-Effective**: Minimal additional infrastructure cost as it builds upon existing Redis instances.
- **Scalability**: Can handle 10x traffic growth (5000 req/s equivalent) with appropriate Redis cluster scaling.

### Negative
- **Durability and Long-Term Retention**: While configurable, Redis Streams are not designed for indefinite message retention at the scale of Kafka. For very long-term archiving, messages would need to be moved to a more persistent store (e.g., S3, PostgreSQL).
- **Extreme Scale Ceiling**: For hypothetical future scaling beyond 10x to truly massive, global event streaming (e.g., millions of events per second sustained), Kafka might offer a higher throughput ceiling and more advanced distributed features. However, this is outside the current 10x growth target.
- **Feature Set**: Redis Streams offer a simpler feature set compared to Kafka. More advanced stream processing paradigms might require additional custom implementation.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-leading capabilities in high-throughput, fault-tolerant, and durable distributed streaming. Its strengths include:
- **High Throughput and Durability**: Designed for petabytes of data and millions of messages per second, with strong durability guarantees.
- **Robust Ecosystem**: Mature ecosystem with connectors, stream processing frameworks (Kafka Streams, Flink), and extensive tooling.
- **Advanced Features**: Supports complex stream processing patterns, long-term data retention, and precise ordering guarantees across partitions.

However, Kafka was rejected due to several critical constraints:
- **Operational Complexity**: Kafka is a notoriously complex distributed system to operate, requiring deep expertise in cluster management, monitoring, and troubleshooting. The team's lack of Kafka experience and absence of a dedicated infrastructure engineer would make self-hosting a significant and risky undertaking.
- **Time-to-Value**: The steep learning curve and operational setup for a robust Kafka cluster would far exceed the 2-week window for delivering initial value.
- **Budget Constraints**: While self-hosting is an option, achieving production-grade resilience and observability would still require significant resource investment, potentially exceeding the modest budget. Managed services like Confluent Cloud would be prohibitively expensive at full scale.
- **Overkill for Current Scale**: While supporting 10x growth is a target, Kafka's full capabilities are likely overkill for the current and projected scale for the next 1-2 years, introducing unnecessary complexity.

The operational burden and the immediate time-to-value requirement were the primary factors in rejecting Kafka at this stage, despite its technical superiority for extreme-scale event streaming.
