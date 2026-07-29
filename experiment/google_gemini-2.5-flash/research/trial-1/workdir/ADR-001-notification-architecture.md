Title: ADR-001 Notification Subsystem Architecture
Status: Proposed

Context:
The current notification module, part of a Python/Flask monolith, synchronously sends emails and webhooks. This has led to critical issues including request timeouts (latency spikes to 8s), silent failures with no retry mechanism, cascading failures due to slow external services, and a complete lack of delivery guarantees, especially for billing-critical notifications.

The platform serves 85,000 monthly active users, generating ~2M tasks per month with peak loads of ~500 req/s. The goal is to decouple notifications, implement retry/dead-letter queues, guarantee at-least-once (and where feasible, exactly-once) delivery for critical events, support 10x traffic growth (to ~5000 req/s peak), and enable real-time WebSocket push notifications within two quarters.

Constraints include a small engineering team of 6 (no dedicated infra engineer, no prior Kafka experience), an existing Redis instance used for caching/rate-limiting, a tight budget (ruling out managed Kafka at full scale), and a strict requirement for initial value delivery within 2 weeks. Exactly-once semantics for billing notifications are non-negotiable.

Decision:
We will adopt **Redis Streams** as the foundation for the new asynchronous notification subsystem.

This decision prioritizes leveraging existing infrastructure and team expertise to meet the immediate operational challenges and delivery timelines, while providing a scalable path for future growth and real-time capabilities. Redis is already running in production for session management and rate limiting, reducing the overhead of introducing a completely new technology stack. The engineering team's familiarity with Redis will significantly shorten the learning curve and accelerate initial setup and migration, easily fitting within the 2-week constraint.

Redis Streams offers native support for consumer groups, message ordering within a stream, and configurable message retention, directly addressing the need for asynchronous processing, retry mechanisms, and reliable message handling. While Redis Streams does not offer the same native distributed transaction guarantees as Kafka for exactly-once semantics, "effectively exactly-once" delivery for billing-critical notifications can be achieved through careful application-level design, such as implementing idempotent consumers and tracking unique message IDs to prevent reprocessing duplicates. This approach is manageable given the team's size and current expertise. The planned 10x traffic growth to ~5000 req/s is well within the capabilities of a properly configured Redis Streams setup, and Redis's existing pub/sub features align well with the future requirement for real-time WebSocket notifications.

Consequences:
Pros:
*   **Reduced Operational Overhead**: Leverages existing Redis infrastructure and team familiarity, minimizing the operational burden of a new distributed system.
*   **Faster Time-to-Value**: Setup and integration are expected to be significantly quicker than Kafka, meeting the 2-week constraint for initial value delivery.
*   **Cost-Effective**: Avoids the immediate high costs associated with managed Kafka solutions at scale.
*   **Scalability**: Redis Streams can handle the projected 10x traffic increase (~5000 req/s) with appropriate architectural considerations (e.g., sharding if needed).
*   **Feature Alignment**: Supports consumer groups, message ordering, message retention, and aligns well with future real-time WebSocket notification requirements.

Cons:
*   **Exactly-Once Semantics Complexity**: Achieving true exactly-once delivery for billing notifications requires more application-level logic (e.g., idempotency keys, state tracking) compared to Kafka's native transactional capabilities.
*   **Long-Term Retention**: Redis Streams are generally less suited for very long-term (months/years) message retention compared to Kafka, though configurable retention can meet immediate needs.
*   **Scalability Ceiling (Extreme Cases)**: While sufficient for current projections, Redis Streams might hit a scalability ceiling earlier than Kafka under extremely high, sustained throughput scenarios far beyond the 10x target, potentially requiring more complex sharding or multi-instance management.
*   **No Integrated Ecosystem for Analytics**: Lacks Kafka's rich ecosystem for stream processing, data warehousing, and analytics integrations, which might be a consideration for future data initiatives.

Alternatives Considered:
**Apache Kafka**:
Kafka was considered due to its industry-leading capabilities for high-throughput, fault-tolerant, and highly scalable distributed streaming. It natively offers strong ordering guarantees, robust consumer groups, and advanced features for exactly-once message processing through transactions. However, it was rejected for the following reasons:
*   **High Operational Complexity**: Kafka introduces significant operational overhead. For a small team with no dedicated infrastructure engineer and no prior Kafka experience, self-hosting Kafka would require substantial time investment in learning, setup, monitoring, and maintenance, far exceeding the 2-week initial value constraint.
*   **Budget Constraints**: While Kafka is open-source, the cost of managed Kafka services (like Confluent Cloud) at the projected scale would exceed the modest budget. Self-hosting and managing Kafka for high availability and performance is a complex and resource-intensive task for which the team is currently unprepared.
*   **Setup Time**: The learning curve and deployment complexity of Kafka would significantly delay the project, making it impossible to deliver initial value within the two-week timeframe. Introducing a new, complex distributed system would likely divert critical engineering resources from product development.