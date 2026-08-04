**Title: ADR-001: Notification Subsystem Architecture**

**Status: Proposed**

**Context**
The existing notification module within our Python/Flask monolith synchronously handles sending emails and webhooks for task updates, assignments, and completions. This approach has led to significant issues:
1.  **Request timeouts**: Notifications block the HTTP request cycle, causing average latencies of 800ms and spikes up to 8 seconds during peak hours.
2.  **Silent failures**: Notifications are dropped without retry or a dead-letter queue if external services (email providers, webhook endpoints) are unavailable.
3.  **Cascading failures**: Slow webhook endpoints have exhausted connection pools, leading to outages in unrelated features.
4.  **No delivery guarantees**: Billing-critical notifications lack at-least-once or exactly-once delivery guarantees.

We need to decouple notification processing from the main request flow to ensure reliability, scalability, and improved user experience. The new subsystem must support retry mechanisms, guarantee at-least-once delivery for billing events (and exactly-once where feasible), and accommodate 10x traffic growth. Furthermore, it should enable the future integration of real-time WebSocket push notifications within two quarters.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We currently use Redis for session storage and rate limiting. There is no prior team experience with Apache Kafka. The solution must be implemented with minimal setup/migration effort (under 2 weeks to deliver initial value) and adhere to a modest budget, ruling out expensive managed Kafka solutions at scale.

**Decision: Redis Streams**
We recommend implementing the notification subsystem using **Redis Streams**. This decision is primarily driven by our team's existing familiarity with Redis, the low operational overhead, and its ability to meet the critical requirements within our constraints.

Redis Streams offers a robust, append-only data structure that functions as a persistent log, supporting multiple consumer groups and at-least-once delivery. Its integration with our existing Redis infrastructure will significantly reduce setup and operational complexity. While Kafka is a more powerful and feature-rich message broker, the learning curve and operational burden for our small team, combined with budget constraints for managed services, make it a less suitable choice for our immediate needs. Redis Streams provides a pragmatic solution that allows us to rapidly address the most pressing issues and lay the groundwork for future scalability, including real-time WebSocket notifications.

**Consequences**

**Pros:**
*   **Reduced Operational Complexity:** Leveraging an existing Redis deployment minimizes the learning curve and operational overhead for our small team with no dedicated infrastructure engineer. Redis is already understood, monitored, and maintained by the team.
*   **Rapid Development & Deployment:** The simplicity of Redis Streams and the existing Redis infrastructure allows for faster initial setup and migration, meeting the "under 2 weeks" constraint.
*   **At-Least-Once Delivery & Consumer Groups:** Redis Streams provides consumer groups, enabling multiple consumers to process messages from a stream with automatic offset tracking, ensuring at-least-once processing semantics for notifications. This directly addresses the silent failure and delivery guarantee problems.
*   **Exactly-Once Semantics (Application-Level):** While Redis Streams provides at-least-once, exactly-once semantics for billing notifications can be achieved at the application level through idempotent processing and careful design (e.g., using transaction IDs and checking for duplicates before processing). This is a manageable trade-off for our team given the other benefits.
*   **Good for Real-time Features:** Redis's low-latency nature and existing presence make it an excellent choice for future real-time WebSocket push notifications, as it can directly serve as a pub/sub mechanism or event source.
*   **Cost-Effective:** Utilizing existing Redis infrastructure or easily deployable open-source Redis instances is more budget-friendly than self-hosting Kafka or using expensive managed Kafka services.
*   **Message Retention:** Redis Streams support configurable message retention, allowing us to store a history of notifications for debugging, auditing, and re-processing.

**Cons:**
*   **Lower Throughput/Scale than Kafka (Potentially):** For extremely high-throughput, high-volume scenarios (tens of millions of messages per second), Redis Streams may not match Kafka's raw performance and horizontal scalability, particularly with a single Redis instance. However, Redis can be scaled with clustering if needed, and our current 500 req/s peak is well within its capabilities.
*   **Fewer Built-in Features for Complex Data Pipelines:** Redis Streams has a simpler feature set compared to Kafka, which offers a broader ecosystem for stream processing, connectors, and advanced analytics. This means more custom logic will be required for complex transformations or integrations.
*   **Less Mature Ecosystem for Enterprise Use Cases:** While growing, the Redis Streams ecosystem is not as mature or as widely adopted for critical enterprise-level message brokering as Kafka, which has extensive tooling and community support.
*   **Memory Footprint:** As Redis is an in-memory database, large stream backlogs can consume significant memory. Careful management of message retention policies will be necessary.

**Alternatives Considered**

**1. Apache Kafka**
Apache Kafka was considered due to its industry-standard position for high-throughput, distributed streaming platforms, offering robust features like strong ordering guarantees, high scalability, and a rich ecosystem for stream processing.

**Reasons for Rejection:**
*   **High Operational Complexity & Learning Curve:** Kafka introduces significant operational complexity (managing Zookeeper/Kraft, brokers, partitions, replication) that would be a substantial burden for our small team of 6 engineers with no dedicated infrastructure expertise and no prior Kafka experience. This directly conflicts with the constraint of minimal setup/migration time and team capabilities.
*   **Budget Constraints:** Running a highly available and scalable Kafka cluster, especially with enterprise features (e.g., exactly-once semantics beyond at-least-once), often requires a managed service like Confluent Cloud. Our "modest budget" and aversion to full-scale managed Confluent Cloud costs rule out this option for initial deployment. Self-hosting Kafka would entail a large upfront investment in learning and operational tooling.
*   **Setup/Migration Time:** The learning curve and infrastructure setup for Kafka would almost certainly exceed the "2 weeks of setup/migration work before delivering value" constraint.
*   **Overkill for Current Scale:** While scalable to extreme levels, Kafka might be an overkill for our current ~2M tasks/month and 500 req/s peak, especially given the operational overhead. Redis Streams can handle this scale effectively.

Kafka remains a viable option for a future, more mature state of our platform with a larger, more specialized infrastructure team, or if our message volume scales beyond what Redis Streams can efficiently handle, even with clustering. For now, its benefits do not outweigh the immediate costs and complexities for our team.