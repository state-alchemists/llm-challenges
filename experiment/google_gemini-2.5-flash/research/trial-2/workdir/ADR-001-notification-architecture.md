# Title: ADR-001: Notification Subsystem Architecture - Redis Streams vs. Apache Kafka

**Status**: Proposed

**Context**
The current SaaS project management platform (85,000 MAU, ~2M tasks/month, peak ~500 req/s) handles notifications synchronously within the HTTP request cycle. This architecture leads to significant issues:
1.  **Request timeouts**: Latency spikes to 8s during peak, blocking user requests.
2.  **Silent failures**: Notifications (emails, webhooks) are dropped on external service failures, with no retry mechanism or dead-letter queue.
3.  **Cascading failures**: External service slowness has caused connection pool exhaustion and outages.
4.  **No delivery guarantees**: Billing-critical notifications lack at-least-once or exactly-once delivery.

The new notification subsystem must:
*   Decouple notifications from the HTTP request cycle for asynchronous processing.
*   Implement retry with exponential backoff.
*   Guarantee at-least-once delivery for all notifications, with exactly-once where feasible for billing events.
*   Support future real-time WebSocket push notifications within two quarters.
*   Scale to handle 10x traffic growth.

**Constraints**:
*   **Team**: 6 engineers (3 senior, 3 mid), no dedicated infrastructure engineer.
*   **Existing Infrastructure**: Redis is already used in production for session management and rate limiting.
*   **Team Experience**: No Kafka experience.
*   **Time to Value**: Must deliver value within 2 weeks of setup/migration.
*   **Budget**: Modest; cannot afford full-scale managed Kafka (e.g., Confluent Cloud).

**Decision**: Choose **Redis Streams** for the notification subsystem.

This decision prioritizes operational simplicity, speed of implementation, and cost-effectiveness, aligning directly with the core team constraints while adequately meeting all scaling and delivery requirements. Leveraging existing Redis infrastructure and team familiarity significantly de-risks the project. While Apache Kafka offers a more robust ecosystem for extreme data streaming, its operational complexity and the team's lack of experience make it an unsuitable choice given the immediate project constraints. Exactly-once semantics for billing notifications can be achieved through idempotent consumer design with Redis Streams.

**Consequences**:

**Pros of Redis Streams:**
*   **Low Operational Overhead**: Since Redis is already deployed and understood by the team, integrating Redis Streams adds minimal operational burden. This is critical for a small team without dedicated infrastructure engineers.
*   **Rapid Development & Deployment**: Leveraging existing Redis instances allows for quick setup and integration, making it feasible to meet the 2-week "value delivery" constraint.
*   **Cost-Effective**: No new infrastructure costs beyond scaling existing Redis, which is already budgeted and managed. Avoids the high cost of managed Kafka services or the significant time investment of self-hosting.
*   **Sufficient Scalability**: Redis Streams offer excellent throughput and horizontal scalability for the projected 10x traffic growth (5000 req/s equivalent), especially for a notification workload that primarily involves small, frequent messages.
*   **Ordering Guarantees**: Messages are strictly ordered within a stream, which is crucial for maintaining event chronology.
*   **Robust Consumer Groups**: Redis Streams' consumer groups provide resilient, fault-tolerant processing, allowing multiple consumers to share the workload and easily recover from failures, ensuring at-least-once delivery.
*   **Real-time Capabilities**: Redis Streams integrate well with Redis Pub/Sub, providing a solid foundation for adding real-time WebSocket push notifications later.
*   **Exactly-Once Feasibility**: While not providing native distributed transactions like Kafka, exactly-once processing for critical billing notifications can be reliably achieved by designing idempotent consumers.

**Cons of Redis Streams:**
*   **Idempotent Consumer Design Required for Exactly-Once**: Achieving true end-to-end exactly-once semantics, especially for external systems, requires careful application-level idempotence in consumers. This adds a layer of design complexity at the application level that Kafka's transactional API might simplify.
*   **Ecosystem Maturity**: The tooling, connectors, and client libraries for Redis Streams are still less mature and extensive compared to the vast Kafka ecosystem. This may require more custom development for integrations.
*   **Scalability at Extreme Edge Cases**: For truly massive, petabyte-scale, multi-datacenter streaming scenarios, Kafka may offer superior raw throughput and cluster management features. However, for the specified 10x growth, Redis Streams are expected to perform adequately.

**Alternatives Considered**:

**Apache Kafka**
Kafka was rejected despite its industry-leading capabilities for high-throughput, fault-tolerant data streaming due to the overwhelming operational and team-skill constraints.

*   **Operational Complexity**: Kafka's architecture (brokers, ZooKeeper/KRaft, topics, partitions, replication) introduces significant operational overhead for setup, maintenance, monitoring, and scaling. This complexity would severely strain a small engineering team with no dedicated infrastructure specialist.
*   **Lack of Team Experience**: The team has no Kafka experience. The steep learning curve for deployment, management, and application development would violate the 2-week "value delivery" constraint and likely extend the project timeline considerably.
*   **Cost**: Managed Kafka services (e.g., Confluent Cloud) would exceed the "modest budget" constraint at scale. Self-hosting Kafka would require substantial investment in VMs and team time, also impacting budget and time.
*   **Time to Value**: Setting up a production-ready, resilient Kafka cluster and integrating it would almost certainly take longer than the mandated 2 weeks, delaying the decoupling of notifications.

While Kafka provides strong native support for exactly-once semantics via transactional APIs and offers a more mature ecosystem, these benefits are outweighed by the practical limitations of the engineering team's size, skill set, budget, and time-to-value requirements. The risk of project delays, increased operational burden, and budget overruns with Kafka is unacceptably high given the current context.
