# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

**Context**
Our SaaS project management platform is experiencing significant issues with its synchronous notification system. With 85,000 monthly active users and 2M tasks created per month, synchronous notification processing leads to request timeouts, silent failures, and cascading system failures due to external dependencies (email providers, webhook endpoints). Billing-critical notifications currently lack delivery guarantees.

We need to decouple notifications from the HTTP request cycle, implement async processing with retry and exponential backoff, guarantee at-least-once delivery for all notifications (and exactly-once for billing events), and support a 10x traffic increase. The system must also support future real-time WebSocket push notifications within two quarters.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We currently use Redis for session storage and rate limiting. There is no existing Kafka experience on the team. The solution must deliver value within two weeks of setup/migration and fit a modest budget, precluding expensive managed Kafka solutions at scale.

**Decision**
We will adopt **Redis Streams** for our notification subsystem.

This decision is primarily driven by the team's existing familiarity with Redis, the modest operational complexity of Redis Streams, and its ability to meet our immediate scaling and delivery guarantees within the stated constraints. While Kafka offers higher throughput and more robust enterprise-grade features, the operational overhead and learning curve for a small team with no prior experience outweigh its benefits for our current stage, especially given budget constraints preventing fully managed Kafka.

Redis Streams directly addresses our need for asynchronous processing, persistent messaging, consumer groups, and at-least-once delivery semantics. With careful implementation of consumer group logic and idempotent consumers, we can achieve exactly-once processing for billing-critical notifications.

**Consequences**

*   **Pros:**
    *   **Low Operational Overhead:** Leverages existing Redis infrastructure and team familiarity, significantly reducing setup, monitoring, and maintenance costs compared to a new Kafka deployment.
    *   **Rapid Implementation:** The existing Redis instance allows for quick prototyping and deployment, aligning with the "2 weeks to value" constraint.
    *   **At-Least-Once Delivery:** Redis Streams inherently supports at-least-once delivery with consumer acknowledgements, resolving the silent failure problem.
    *   **Exactly-Once Feasibility:** Achievable for critical notifications by designing idempotent consumers combined with Redis Streams' consumer groups and message IDs.
    *   **Built-in Retry/Backoff:** Can be implemented on the consumer side by not acknowledging messages immediately on failure, allowing re-processing.
    *   **Scalability for 10x Growth:** Redis Streams can handle the projected 10x traffic increase, especially with proper scaling of Redis instances and consumer groups.
    *   **Real-time Capabilities:** Excellent fit for future WebSocket push notifications due to Redis's low-latency nature and pub/sub capabilities, which complement Streams.
    *   **Cost-Effective:** Avoids the significant costs associated with managed Kafka services or the infrastructure burden of self-hosting Kafka.

*   **Cons:**
    *   **Lower Throughput Ceiling:** While sufficient for 10x growth (5k req/s), Redis Streams has a lower theoretical throughput ceiling than Kafka for extreme scale. This is a trade-off we accept given our current constraints.
    *   **Complexity for Exactly-Once:** Achieving true exactly-once semantics requires careful design of idempotent consumers and state management, which adds application-level complexity compared to Kafka's more robust transactional features.
    *   **Limited Ecosystem Maturity:** Redis Streams' ecosystem, while growing, is not as mature or feature-rich as Kafka's for complex data pipelines and integrations.
    *   **Storage Management:** Retention policies and data compaction need to be carefully managed (e.g., using `XTRIM`) to prevent unbounded growth of stream data, which is a manual consideration compared to Kafka's default behaviors.

**Alternatives Considered**

*   **Apache Kafka:**
    *   **Why rejected:** While Kafka is a powerful, high-throughput, and highly scalable distributed streaming platform with robust exactly-once semantics and a mature ecosystem, it was rejected primarily due to our team's constraints. The absence of Kafka experience on the 6-person engineering team, coupled with the "modest budget" constraint that prevents managed Confluent Cloud at full scale, makes self-hosting or learning Kafka within a 2-week "value delivery" window infeasible. The operational complexity and steep learning curve would divert critical engineering resources from product development, exceeding our initial setup/migration time and budget allowances. While Kafka's native exactly-once semantics are superior, the cost and expertise barrier are too high for our current situation. The long-term architectural benefits of Kafka are clear, but not at the expense of our immediate project viability and team capacity.