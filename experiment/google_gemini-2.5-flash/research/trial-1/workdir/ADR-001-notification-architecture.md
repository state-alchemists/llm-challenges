Title: ADR-001: Notification Subsystem Architecture Decision

Status: Proposed

Context
The existing notification module within our Python/Flask monolith synchronously sends emails and webhooks, leading to significant performance and reliability issues. These include request timeouts (average 800ms, peaks to 8s), silent failures with no retry mechanism, and cascading failures caused by slow external services. Critically, there are no delivery guarantees, which is unacceptable for billing-critical notifications that require exactly-once semantics.

Our goal is to decouple notification processing from the HTTP request cycle, introduce asynchronous processing, implement retry mechanisms with exponential backoff, and guarantee at-least-once delivery (with exactly-once for billing events). The solution must also support a future transition to real-time WebSocket push notifications and scale to 10x current traffic.

Constraints:
*   Engineering team of 6 (3 senior, 3 mid) with no dedicated infrastructure engineer.
*   Existing Redis infrastructure is already in production for session management and rate limiting.
*   No prior team experience with Apache Kafka.
*   Initial setup and migration must deliver value within two weeks.
*   Modest budget; managed Kafka solutions like Confluent Cloud are not viable at full scale.
*   Exactly-once semantics are mandatory for billing notifications.

Decision
We will implement the notification subsystem using **Redis Streams**.

This decision is primarily driven by the team's current capabilities, existing infrastructure, and the tight timeline for initial value delivery, while still meeting critical scaling and delivery guarantees. Redis Streams offers a robust, log-like data structure within an already familiar and deployed technology stack.

1.  **Operational Simplicity & Existing Expertise**: Our team already operates Redis in production. Integrating Redis Streams leverages existing knowledge, reducing the operational burden and learning curve significantly compared to introducing Kafka, which has no prior team experience. This directly addresses the constraint of "no dedicated infrastructure engineer" and the "max 2 weeks setup/migration" timeline.
2.  **Performance and Scalability**: Redis Streams provides excellent throughput, capable of handling our current ~500 req/s peak and scaling to 10x traffic. Its append-only log structure and consumer groups are well-suited for message queueing and parallel processing.
3.  **Delivery Guarantees**: Redis Streams supports at-least-once delivery by tracking consumer group offsets, ensuring messages are processed. For exactly-once semantics with billing notifications, we will implement idempotent consumers. This aligns with our requirement for exactly-once where feasible and mandatory for billing.
4.  **Cost-Effectiveness**: Leveraging our existing self-managed Redis instance keeps costs low, fitting within the "modest budget" constraint.
5.  **Future Real-time Notifications**: Redis's pub/sub capabilities, combined with Streams for persistent event logging, make it a strong foundation for future real-time WebSocket push notifications.

Consequences

Pros:
*   **Rapid Development & Deployment**: Low learning curve due to existing Redis expertise enables quick integration and initial value delivery within the 2-week constraint.
*   **Reduced Operational Overhead**: No new distributed system to manage, reducing infrastructure complexity and the need for a dedicated infra engineer.
*   **Cost-Effective**: Utilizes existing Redis infrastructure, avoiding the costs associated with new Kafka clusters or expensive managed services.
*   **Robust Delivery**: Provides at-least-once delivery with consumer groups and supports idempotent consumers for exactly-once semantics, addressing critical reliability issues.
*   **Scalability**: Capable of handling significant message volumes and supporting future growth (10x traffic).
*   **Real-time Potential**: A good foundation for adding real-time WebSocket notifications later.

Cons:
*   **Limited Message Size**: While generally sufficient for notification payloads, very large messages might require external storage and a pointer in Redis Stream.
*   **Maturity (compared to Kafka)**: Redis Streams is a relatively newer feature compared to Kafka, which has a more mature ecosystem for advanced stream processing. However, for a notification subsystem, Redis Streams features are sufficient.
*   **Monitoring and Tooling**: While Redis has good monitoring, the ecosystem for Redis Streams specific observability might be less mature than Kafka's. This may require some custom dashboarding.
*   **No Built-in Transactional Producer/Consumer**: Achieving exactly-once semantics requires careful implementation of idempotent consumers and transactional logic within the application layer. Kafka offers more robust transactional guarantees out-of-the-box.

Alternatives Considered

Apache Kafka

*   **Reasons for Rejection**:
    *   **High Operational Complexity**: Kafka is a powerful but complex distributed system to set up, operate, and troubleshoot, especially for a team with "no dedicated infrastructure engineer" and "no Kafka experience." This directly conflicts with our "max 2 weeks setup/migration" constraint.
    *   **Learning Curve**: The steep learning curve for the entire team to become proficient in Kafka would delay initial delivery and increase project risk.
    *   **Budget Constraints**: While self-hosting is possible, achieving high availability and performance with Kafka requires significant operational expertise and resources. Managed solutions like Confluent Cloud are out of budget.
    *   **Overkill for Initial Needs**: While Kafka excels at massive-scale data pipelines and complex stream processing, its full feature set is more than what is immediately required for our notification subsystem. The overhead of introducing it outweighs the benefits given our constraints.
    *   **Initial Value Delivery**: The time spent on learning, setup, and stabilization of a new Kafka cluster would significantly exceed the 2-week target for delivering initial value.

The primary blockers for Kafka are the operational complexity, the lack of team experience, and the tight timeline, making it an unsuitable choice for our immediate needs and team profile despite its technical prowess for very large-scale event streaming.