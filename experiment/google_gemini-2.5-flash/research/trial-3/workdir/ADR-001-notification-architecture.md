**Title**: ADR-001: Notification Subsystem Architecture Decision
**Status**: Proposed

**Context**
The existing notification module within our Python/Flask monolith synchronously handles emails and webhooks, leading to critical performance and reliability issues. These include request timeouts (latency spikes to 8s), silent failures with no retry mechanism, cascading failures due to slow external endpoints, and a complete lack of delivery guarantees for critical notifications (e.g., billing events).

Our scaling targets require decoupling notifications from the HTTP request cycle for asynchronous processing, implementing retry mechanisms, guaranteeing at-least-once delivery for billing events (and exactly-once where feasible), supporting 10x traffic growth, and enabling real-time WebSocket push notifications within two quarters.

Key constraints influencing this decision include an engineering team of 6 with no dedicated infrastructure engineer, existing Redis infrastructure used for caching and rate limiting, no prior team experience with Kafka, a strict limit of 2 weeks for initial setup and migration to deliver value, and a modest budget precluding expensive managed Kafka solutions at full scale. Maintaining exactly-once semantics for billing notifications is crucial.

**Decision**
We will implement the new asynchronous notification subsystem using **Redis Streams**. This decision prioritizes operational simplicity, speed of implementation, and leveraging existing infrastructure over the raw scalability and advanced native features of Apache Kafka, which are currently not critical given our team size and budget constraints.

Redis Streams will be used as the message broker to enqueue notifications. A separate pool of consumer workers will read from these streams, process notifications (sending emails, webhooks), and manage retries. Consumer groups will allow for scalable and resilient processing, while Redis's built-in persistence will ensure message durability.

**Consequences**
*   **Pros:**
    *   **Lower Operational Overhead**: As Redis is already in production and managed by the team, adding Streams functionality requires minimal new operational knowledge or infrastructure. This significantly reduces the burden on our small engineering team, which lacks a dedicated infrastructure engineer.
    *   **Faster Time to Value**: Leveraging existing Redis and its simpler API means a much quicker setup and migration, aligning with the "2 weeks to value" constraint.
    *   **Cost-Effective**: No new infrastructure costs are incurred, and the existing Redis instance can likely handle the initial load, keeping within the modest budget.
    *   **Sufficient for Current Scale and Growth**: Redis Streams are capable of handling the current 500 req/s peak and the projected 10x growth within the next 2-3 years, providing necessary decoupling, retry support, and at-least-once delivery guarantees.
    *   **Seamless Integration**: Given Redis is already used in our Python/Flask application, integration with existing code will be more straightforward.
    *   **Supports WebSocket Notifications**: Redis Streams can effectively backend real-time WebSocket push notifications, fulfilling future requirements.

*   **Cons:**
    *   **Complex Exactly-Once Semantics**: While Redis Streams provide at-least-once delivery guarantees (which is sufficient for billing events with idempotent consumers), achieving true exactly-once semantics might require more complex application-level logic and external coordination compared to Kafka's native transactional API.
    *   **Scalability Beyond 10x**: For scaling significantly beyond the 10x target (e.g., 100x), Redis Streams may eventually hit limitations where Kafka's distributed architecture would be inherently more robust and performant. This is a longer-term concern but should be acknowledged.
    *   **Maturity of Ecosystem**: The Redis Streams ecosystem, while robust, is not as mature or as feature-rich as Kafka's, especially regarding advanced monitoring, data integration, and enterprise tooling.

**Alternatives Considered**

**Apache Kafka**
Kafka was considered for its high-throughput, fault-tolerant, and highly scalable distributed streaming platform capabilities. Its strong ordering guarantees, robust consumer group management, and native support for transactional, exactly-once semantics (Kafka Streams, idempotent producers) were attractive, particularly for billing-critical notifications.

However, Kafka was rejected primarily due to our significant constraints:
*   **Operational Complexity**: Kafka is a complex distributed system that requires significant operational expertise to set up, tune, and maintain. Our team of 6, without a dedicated infrastructure engineer and no prior Kafka experience, would face a steep learning curve and a substantial operational burden that conflicts with our "modest budget" and "fast time to value" requirements.
*   **Budget**: While self-hosting is an option, the operational overhead would be significant. Managed Kafka services (like Confluent Cloud) would exceed our modest budget at scale.
*   **Time to Value**: The learning curve and setup for Kafka would far exceed the "2 weeks of setup/migration work before delivering value" constraint.

While Kafka offers superior capabilities for extreme scale and complex stream processing, its operational cost and learning curve make it an inappropriate choice for our current team and resource constraints. Redis Streams provides a more pragmatic, immediately implementable, and cost-effective solution that meets our immediate scaling targets and reliability needs.