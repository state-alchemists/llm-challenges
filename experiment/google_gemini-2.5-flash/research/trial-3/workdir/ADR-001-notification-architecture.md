# Architecture Decision Record 001: Notification Subsystem

## Status
Proposed

## Context
The existing notification module within our Python/Flask monolith synchronously handles sending emails and webhooks during the HTTP request cycle. This has led to significant issues, including request timeouts (average 800ms, spiking to 8s), silent failures with no retry for external service downtime, cascading failures due to connection pool exhaustion from slow webhook endpoints, and a complete lack of delivery guarantees, which is critical for billing-related notifications.

Our scaling targets require decoupling notifications for asynchronous processing, implementing retry with exponential backoff, guaranteeing at-least-once delivery for all events, ensuring exactly-once delivery for billing-critical events, supporting future real-time WebSocket push notifications, and handling 10x traffic growth.

Key constraints include a small engineering team of 6 (no dedicated infrastructure engineer), existing Redis in production, no current Kafka experience, a hard limit of 2 weeks for initial setup/migration to deliver value, and a modest budget precluding expensive managed Kafka solutions at full scale.

## Decision
We choose **Redis Streams** as the foundation for our new asynchronous notification subsystem.

This decision is primarily driven by our team's existing operational experience with Redis and the strict time and budget constraints. Redis Streams provides the necessary core capabilities for message queuing, persistent logging, and consumer groups to meet our immediate scaling targets (decoupling, retry, at-least-once delivery). The ability to leverage our existing Redis infrastructure and operational knowledge significantly reduces the initial setup and migration burden, aligning with the "2 weeks to value" constraint. While Kafka offers more advanced features for large-scale, high-throughput data streaming, its operational complexity and the team's lack of experience with it present a higher initial barrier that our current constraints cannot accommodate. Redis Streams' simplicity and familiar ecosystem allow for rapid iteration and deployment. For exactly-once semantics, we will implement idempotent consumers and application-level deduplication, which is a feasible pattern with Redis Streams.

## Consequences

### Pros of Redis Streams:
-   **Low Operational Complexity:** We already run Redis in production, reducing the learning curve and operational overhead for the team. This directly addresses the constraint of having no dedicated infrastructure engineer.
-   **Rapid Time to Value:** Setup and integration are expected to be fast, likely within the 2-week target, as it leverages existing infrastructure and familiar tools.
-   **Persistent Messaging:** Provides a durable log of messages, enabling consumers to read from arbitrary points and supporting replay for retry mechanisms.
-   **Consumer Groups:** Built-in support for distributing messages among multiple consumers and tracking their progress, which is essential for scaling out notification processing.
-   **At-Least-Once Delivery:** Achievable with consumer acknowledgments and retry logic.
-   **Cost-Effective:** Leverages existing Redis instances, keeping infrastructure costs down, especially compared to self-hosting Kafka or expensive managed Kafka services.
-   **Suitable for Real-Time:** Its low-latency nature is well-suited for future WebSocket push notification requirements.

### Cons of Redis Streams:
-   **Lower Throughput/Scale than Kafka:** While capable of handling our current and 10x projected load (~500 req/s * 10 = 5000 req/s, translating to notifications), Kafka is designed for significantly higher message volumes and data retention over longer periods. We may hit scaling limits with Redis Streams at much larger scales (e.g., 100x traffic) than Kafka.
-   **Limited Ecosystem/Tooling compared to Kafka:** Kafka has a vast ecosystem of connectors, stream processing frameworks (Kafka Streams, ksqlDB), and monitoring tools that Redis Streams lacks. This may require more custom development for complex data pipelines.
-   **Exactly-Once Semantics:** Not natively supported by Redis Streams in the same way as Kafka's transactional API. This will require careful implementation of idempotent consumers and application-level deduplication logic to ensure billing-critical notifications are processed exactly once. This increases application code complexity.
-   **Data Retention:** Redis Streams retains messages until explicitly trimmed or evicted. While configurable, managing long-term, large-scale data retention can be more complex than in Kafka, which is designed for this.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-leading capabilities in high-throughput, fault-tolerant, distributed streaming.

#### Reasons for Rejection:
-   **Operational Complexity:** Kafka introduces significant operational overhead. Our team has no prior Kafka experience and no dedicated infrastructure engineer. Deploying, managing, and troubleshooting a Kafka cluster would require substantial learning and investment, violating the "2 weeks to value" and team size constraints.
-   **Setup/Migration Time:** The initial setup and integration of Kafka would likely exceed the 2-week constraint due to its steeper learning curve and the need to establish new operational practices.
-   **Cost:** While open-source, self-hosting Kafka requires significant compute and storage resources, and managed services like Confluent Cloud are currently out of our modest budget at full scale.
-   **Overkill for Immediate Needs:** While Kafka's throughput and long-term retention capabilities are superior, they are overkill for our immediate problem and projected 10x growth. Redis Streams can meet the current scaling targets more efficiently given our constraints.
-   **Exactly-Once Trade-offs:** While Kafka offers strong exactly-once semantics through its transactional API, the complexity of implementing this correctly, combined with the overall operational burden, makes it less attractive for our current team and timeline.
