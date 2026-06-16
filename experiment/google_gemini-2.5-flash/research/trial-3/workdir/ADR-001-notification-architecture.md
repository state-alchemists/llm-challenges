# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification module within our Python/Flask monolith synchronously sends emails and webhooks, leading to significant performance and reliability issues. These include request timeouts (latency spikes to 8s), silent failures without retry, and cascading failures due to slow external webhook endpoints. Crucially, there are no delivery guarantees, which is unacceptable for billing-critical notifications.

We need to re-architect the notification subsystem to:
- Decouple notifications from the HTTP request cycle for asynchronous processing.
- Implement retry mechanisms with exponential backoff.
- Guarantee at-least-once delivery for all events, and exactly-once delivery for billing-critical notifications.
- Support 10x traffic growth without requiring another re-architecture.
- Pave the way for real-time WebSocket push notifications within two quarters.

Our engineering team consists of 6 people with no dedicated infrastructure engineer and no prior Kafka experience. We already operate a Redis instance for caching and rate limiting. The solution must be implementable with minimal setup/migration (under 2 weeks to deliver value) and within a modest budget, ruling out expensive managed services like Confluent Cloud at full scale.

## Decision
We choose **Redis Streams** as the foundation for the new notification subsystem.

This decision is driven primarily by our team's existing operational expertise with Redis, the imperative for rapid implementation (under 2 weeks), and budget constraints. Redis Streams provides the necessary primitives for asynchronous processing, reliable delivery (at-least-once with consumer groups, and exactly-once achievable with idempotent consumers), and efficient handling of the projected 10x traffic growth. Its lightweight nature and ease of integration into our existing Redis infrastructure minimize operational overhead and learning curve for the team.

## Consequences

### Pros
*   **Lower Operational Complexity**: Leverages our existing Redis deployment and team familiarity, significantly reducing setup time and ongoing maintenance compared to a new, complex distributed system.
*   **Rapid Development & Deployment**: Integrates quickly with our Python/Flask application. The learning curve for Redis Streams is far less steep than Kafka, allowing us to meet the "under 2 weeks to value" constraint.
*   **Cost-Effective**: Avoids the significant infrastructure costs associated with new Kafka clusters or managed services like Confluent Cloud.
*   **Exactly-Once Semantics**: Achievable for billing notifications through careful implementation of idempotent consumers and Redis Streams' message IDs.
*   **Scalability**: Consumer groups allow for horizontal scaling of notification processors, capable of handling 10x traffic growth.
*   **Real-time Capabilities**: Redis is well-suited for real-time scenarios, aligning with our future goal of WebSocket push notifications.

### Cons
*   **Durability and Long-Term Retention**: While Redis Streams offers message persistence, Kafka is designed for superior long-term data retention and very high-volume historical replay, which Redis Streams may not match at extreme scale. We will need to define appropriate stream length limits and potentially archive older data.
*   **Ecosystem Maturity**: The Redis Streams ecosystem, while growing, is not as mature or feature-rich as Kafka's for complex stream processing, monitoring, and integration with big data tools. However, this is not an immediate requirement.
*   **Throughput Limits**: While sufficient for our 10x growth target, Redis Streams has lower absolute throughput limits compared to a well-tuned Kafka cluster for truly massive, enterprise-grade streaming scenarios. This is a trade-off accepted for the current constraints.

## Alternatives Considered

### Apache Kafka
Apache Kafka was considered due to its industry-leading capabilities in high-throughput, fault-tolerant, distributed streaming.

#### Reasons for Rejection
*   **High Operational Complexity**: Kafka introduces significant operational overhead. Our team of 6, lacking a dedicated infrastructure engineer and any prior Kafka experience, would struggle with setup, configuration, monitoring, and maintenance. This would drastically exceed the "under 2 weeks to value" constraint.
*   **Learning Curve**: The steep learning curve for Kafka's concepts (topics, partitions, brokers, Zookeeper/Kraft, consumer groups, offsets, replication) would divert significant engineering effort from product development.
*   **Budget Constraints**: Managed Kafka services (e.g., Confluent Cloud) are expensive and outside our "modest budget" constraint at full scale. Self-hosting Kafka would entail substantial hidden costs in terms of engineering time and expertise.
*   **Setup Time**: Deploying and integrating a robust Kafka cluster, even in a simplified form, would take far longer than the allotted two weeks, delaying critical decoupling.
*   **Overkill for Current Needs**: While Kafka offers extreme scalability, it is over-engineered for our current (and projected 10x) notification volume given the team's capacity and immediate budget. The benefits of its advanced features do not outweigh the cost of adoption for this specific problem.
