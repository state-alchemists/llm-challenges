## ADR-001-notification-architecture.md

### Title
ADR-001: Notification Subsystem Architecture Decision - Redis Streams vs. Apache Kafka

### Status
Proposed

### Context
The existing notification module within our Python/Flask monolith synchronously handles emails and webhooks, leading to critical performance and reliability issues. These include request timeouts (avg 800ms, peak 8s), silent failures with no retry or dead-letter queue, and cascading failures due to slow external endpoints. Crucially, billing-critical notifications lack delivery guarantees, posing a significant business risk.

Our objective is to decouple notifications from the HTTP request cycle, support retry mechanisms, guarantee at-least-once delivery for all events, and achieve exactly-once semantics for billing-critical notifications. The new system must also support future real-time WebSocket push notifications within two quarters and handle 10x traffic growth without requiring another major re-architecture.

Key constraints influencing this decision are:
*   **Team Size & Expertise:** A 6-person engineering team (3 senior, 3 mid-level) with no dedicated infrastructure engineer.
*   **Existing Infrastructure:** We already run Redis in production for session management and rate limiting, but have no prior Kafka experience.
*   **Time to Value:** Must deliver initial value within 2 weeks of setup/migration.
*   **Budget:** Modest, precluding full-scale managed Kafka solutions like Confluent Cloud.
*   **Delivery Guarantee:** Absolute requirement for exactly-once semantics for billing notifications.

### Decision
We choose **Redis Streams** for the notification subsystem.

This decision prioritizes leveraging existing infrastructure, minimizing operational overhead for our small team, and achieving a faster time to value while still meeting critical scalability and delivery guarantee requirements. Redis Streams provides the necessary features for asynchronous message processing, robust consumer groups, and at-least-once delivery. With careful application-level design, it can also achieve the required exactly-once semantics for billing-critical notifications.

### Consequences

**Pros of Redis Streams:**
*   **Lower Operational Complexity & Learning Curve:** As Redis is already in production and the team has some familiarity, the operational overhead and learning curve for Redis Streams will be significantly lower than introducing a new technology like Kafka. This directly addresses the constraint of having no dedicated infrastructure engineer and a modest budget.
*   **Faster Time to Value:** The existing Redis instance and team familiarity allow for quicker setup and integration, making the "must not require more than 2 weeks of setup/migration work before delivering value" constraint achievable.
*   **Cost-Effective:** Utilizing the existing Redis infrastructure is more budget-friendly than deploying and managing a new Kafka cluster or subscribing to a fully-managed Kafka service at scale.
*   **Good for Real-time:** Redis Streams' low-latency nature makes it well-suited for supporting future real-time WebSocket push notifications.
*   **At-Least-Once Delivery:** Easily achievable with consumer groups and explicit acknowledgment, addressing silent failures and retry requirements.
*   **Exactly-Once Feasibility:** While not inherently "exactly-once" for complex distributed scenarios like Kafka Streams, it is achievable for our billing notifications through idempotent consumer processing combined with Redis Streams' message ID for deduplication, addressing our critical delivery guarantee.

**Cons of Redis Streams:**
*   **Message Retention Management:** Redis Streams retains messages until explicitly truncated. For long-term historical data or unlimited replay, this requires a clear retention policy and potentially external archiving, adding management overhead.
*   **Scalability at Extreme Peaks:** While capable of handling 10x current traffic, Redis Streams might not scale to the *extreme* throughput levels that a fully optimized Kafka cluster could handle for scenarios significantly beyond our projected growth. This is a trade-off accepted given current constraints.
*   **Ecosystem Maturity:** The ecosystem around Redis Streams, while growing, is less mature and extensive compared to Kafka's vast tooling (e.g., Kafka Connect for easy integrations).
*   **Exactly-Once Implementation Complexity:** Achieving robust exactly-once semantics for all messages across complex failure scenarios might require more custom application-level logic and careful design compared to Kafka's built-in support via its Streams API.

### Alternatives Considered

**Apache Kafka:**
Apache Kafka was considered due to its industry-leading capabilities in high-throughput, fault-tolerant, and horizontally scalable distributed streaming. It offers robust features like inherent long-term message retention, strong ordering guarantees, and advanced consumer group management. Furthermore, Kafka's ecosystem, particularly Kafka Streams, provides powerful primitives for implementing exactly-once semantics across complex processing pipelines, directly addressing our need for billing-critical notifications.

However, Kafka was rejected primarily due to the significant operational complexity and steep learning curve it would introduce for our 6-person engineering team, which lacks dedicated infrastructure expertise and has no prior Kafka experience. The constraint of delivering value within 2 weeks of setup/migration would be extremely challenging to meet with Kafka, as setting up, configuring, and properly operating a Kafka cluster (even a small one) requires considerable upfront effort and specialized knowledge. Our modest budget also prevents the use of a fully-managed, full-scale Confluent Cloud solution, which would otherwise mitigate some of the operational burden. While Kafka's technical merits for large-scale event streaming are superior, the immediate team and budget constraints make it an unsuitable choice for our current needs and stage.