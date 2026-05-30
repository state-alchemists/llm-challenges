# ADR-001: Notification Subsystem Architecture

**Title**: Notification Subsystem Architecture

**Status**: Proposed

**Context**
Our SaaS project management platform's synchronous notification system is causing request timeouts, silent failures, cascading failures, and lacks delivery guarantees. We currently handle 85,000 monthly active users and ~2M tasks created per month, with peak traffic at ~500 req/s. We need to decouple notifications from the HTTP request cycle, support retries with exponential backoff, guarantee at-least-once delivery for billing events (exactly-once where feasible), and prepare for real-time WebSocket push notifications within two quarters, handling 10x traffic growth without re-architecture.

Our engineering team of 6 has no dedicated infrastructure engineer and no Kafka experience. We already use Redis for caching, and our budget is modest, precluding expensive managed Kafka solutions. Setup and migration must be achievable within two weeks to deliver value.

**Decision**
We will adopt **Redis Streams** for our notification subsystem.

This decision is based on Redis Streams' ability to meet our immediate needs for decoupling, retry, and delivery guarantees, while leveraging existing team expertise and infrastructure, and minimizing setup time and operational complexity. Its built-in consumer group functionality, message retention, and support for at-least-once delivery are critical. With careful implementation, exactly-once semantics for billing events can be achieved by combining Redis Streams' features with application-level idempotency.

**Consequences**

**Pros of Redis Streams:**
*   **Low Operational Complexity**: We already operate Redis, so adding Streams introduces minimal new operational overhead. This is crucial for our small team with no dedicated infrastructure engineer.
*   **Fast Time to Value**: Leveraging existing Redis infrastructure means a quicker setup and migration, aligning with the "2 weeks to value" constraint.
*   **Cost-Effective**: No need for new infrastructure or expensive managed services like Confluent Cloud, fitting our modest budget.
*   **Consumer Groups**: Redis Streams natively supports consumer groups, enabling multiple consumers to process the same stream of messages collaboratively, ensuring each message is processed only once by a group member.
*   **At-Least-Once Delivery**: With consumer groups and persistent storage, Redis Streams guarantees at-least-once delivery, which is suitable for most notifications and can be enhanced to exactly-once with idempotency for critical billing events.
*   **Message Retention**: Configurable message retention allows for debugging and replaying events.
*   **Built-in for WebSocket Integration**: Redis's pub/sub capabilities are a natural fit for future real-time WebSocket push notifications.

**Cons of Redis Streams:**
*   **Scalability for 10x Growth**: While good for current and initial growth, Redis Streams might require more careful sharding and scaling strategies than Kafka for sustained 10x traffic on billing-critical events, which need exactly-once guarantees. Achieving true horizontal scalability for a single stream may become a bottleneck.
*   **Exactly-Once Semantics (Application-level)**: While at-least-once is guaranteed, achieving exactly-once semantics for billing notifications will require careful application-level idempotency logic, adding development complexity. It is not an inherent feature of Redis Streams in the same way as it is with Kafka transactions.
*   **Limited Ecosystem**: Compared to Kafka, the ecosystem for monitoring, tooling, and connectors around Redis Streams is less mature.
*   **Ordering Guarantees (within a stream)**: While message order is guaranteed within a single stream, cross-stream ordering (if multiple streams are used for a single logical flow) requires application-level coordination.

**Alternatives Considered**

**Apache Kafka**

Kafka was considered due to its robust features, high throughput, and strong guarantees, particularly for exactly-once semantics through transactions. However, it was rejected for the following reasons:

*   **High Operational Complexity**: Kafka is a distributed system with significant operational overhead, requiring dedicated expertise for setup, maintenance, and troubleshooting. Our team lacks Kafka experience and a dedicated infrastructure engineer, making it a high-risk option for our team size.
*   **Longer Time to Value**: The learning curve and infrastructure setup for Kafka would exceed our two-week constraint for delivering value.
*   **Higher Cost**: Running Kafka, especially with the throughput required for 10x growth, would likely push us towards managed services like Confluent Cloud, which are currently outside our modest budget. Self-hosting Kafka would require significant engineering effort and potentially higher infrastructure costs.
*   **Overkill for Initial Needs**: While powerful for extreme scale, Kafka's full feature set might be an over-engineering choice for our immediate problems and current scale. We can achieve the required decoupling and delivery guarantees with a simpler solution initially.
*   **Resource Intensive**: Kafka clusters can be resource-intensive, potentially increasing our infrastructure footprint and costs significantly compared to extending our existing Redis usage.