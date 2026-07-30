Title: ADR-001-Notification-Subsystem-Architecture
Status: Proposed
Context

The current notification system, integrated synchronously within the Python/Flask monolith, is causing critical performance and reliability issues. Request timeouts, silent failures, cascading failures, and a lack of delivery guarantees (especially for billing-critical events) are impacting user experience and business operations.

The objective is to decouple notification processing, introduce asynchronous handling, implement robust retry mechanisms, and guarantee at-least-once delivery for all notifications, with exactly-once semantics for billing-critical events. The new system must also support future real-time WebSocket push notifications and scale to 10x current traffic.

Key constraints include a small engineering team (6 people, no dedicated infrastructure), existing Redis usage, no prior Kafka experience, a tight 2-week setup/migration timeline for initial value, and a modest budget precluding expensive managed Kafka solutions at full scale.

Decision

We choose Redis Streams for the notification subsystem.

While Apache Kafka offers robust features for large-scale distributed streaming, Redis Streams provides a significantly lower operational overhead and a faster path to value, aligning better with our team's size, existing Redis expertise, and tight timeline. The ability to leverage an existing Redis instance simplifies deployment and management, while its feature set adequately addresses our current and near-future scaling and delivery requirements, including consumer groups, message retention, and the foundation for exactly-once processing.

Consequences

Pros of Redis Streams:

*   Operational Simplicity: As an existing technology in our stack, Redis Streams introduces minimal operational complexity. Our team already manages Redis for caching, reducing the learning curve for deployment, monitoring, and troubleshooting. This directly addresses the constraint of a small engineering team without a dedicated infrastructure engineer.
*   Faster Time to Value: Leveraging existing infrastructure and team familiarity means we can implement and deploy the new notification system much faster than with Kafka. This aligns with the "not require more than 2 weeks of setup/migration work before delivering value" constraint.
*   Cost-Effective: Utilizing our existing Redis setup minimizes additional infrastructure costs, fitting within our modest budget constraint. We avoid the immediate need for managed Kafka services, which can be expensive.
*   Consumer Groups: Redis Streams support consumer groups, enabling distributed consumption of messages, load balancing, and fault tolerance among worker instances, satisfying the asynchronous processing requirement.
*   Message Retention: Configurable message retention allows us to store messages for retries and auditing.
*   Exactly-Once Semantics (Feasible): While not inherently "exactly-once" out-of-the-box, Redis Streams, combined with idempotent consumers and tracking processed message IDs in PostgreSQL (as outlined in the TodoRead items), can achieve exactly-once processing for billing-critical notifications. The XACK command for acknowledging messages and consumer group persistence are key enablers here.
*   Future-Proofing for WebSockets: Redis's pub/sub capabilities complement Redis Streams, making it a strong candidate for future real-time WebSocket push notifications, providing a unified messaging layer.

Cons of Redis Streams:

*   Scalability Limits (eventual): While Redis Streams can handle significant throughput (10x growth is achievable), for extreme, petabyte-scale streaming workloads, Kafka's distributed architecture offers superior raw performance and partitioning capabilities. We may eventually hit limits if traffic grows orders of magnitude beyond the 10x target, requiring re-evaluation.
*   Durability and Replication: Redis persistence (RDB/AOF) provides good durability, but Kafka's architecture is fundamentally designed for higher data durability and fault tolerance across a cluster of brokers. While Redis replication can mitigate some risks, it might not be as robust in catastrophic failure scenarios as a well-configured Kafka cluster.
*   Ecosystem Maturity: Kafka has a more mature and extensive ecosystem of connectors, tools, and clients for various data integration patterns. Redis Streams' ecosystem is growing but not as comprehensive.
*   Learning Curve for Advanced Features: While basic usage is simple, mastering advanced Redis operational patterns and ensuring optimal performance for Streams might still present a learning curve for the team.

Alternatives Considered

Apache Kafka

Apache Kafka was considered due to its industry-leading capabilities for high-throughput, fault-tolerant, and scalable distributed streaming. Its strengths include:

*   High Throughput and Scalability: Kafka is designed for handling millions of messages per second and scales horizontally with ease, making it suitable for massive data pipelines.
*   Robust Durability and Fault Tolerance: Data is replicated across multiple brokers, providing strong durability guarantees and high availability.
*   Strong Ordering Guarantees: Messages within a partition are strictly ordered.
*   Mature Ecosystem: A vast array of connectors (Kafka Connect) for integration with databases, analytics systems, and other services, along with extensive tooling.

Reasons for Rejection:

*   High Operational Complexity: Kafka requires significant operational expertise to set up, tune, and maintain a production-grade cluster. Given our team's size (6 engineers, no dedicated infrastructure engineer) and lack of prior Kafka experience, this would place an undue burden on the team and directly conflict with our "not require more than 2 weeks of setup/migration" constraint.
*   Budget Constraints: Running a self-managed Kafka cluster robustly is complex and resource-intensive. Managed services like Confluent Cloud, while simplifying operations, are costly, exceeding our "modest budget" at full scale.
*   Steeper Learning Curve: The entire team would need to acquire new skills in Kafka administration, development, and troubleshooting, which would significantly slow down initial development and delivery. This conflicts with the goal of delivering value quickly.
*   Overkill for Current Needs: While powerful, Kafka's full capabilities are likely an over-solution for our immediate notification needs. Redis Streams can meet the current requirements (10x growth, at-least-once, feasible exactly-once) with significantly less overhead.

The decision to proceed with Redis Streams is a pragmatic choice that balances the technical requirements with our team's capabilities, budget, and project timeline. It provides a solid foundation for our notification subsystem while minimizing immediate risk and maximizing developer velocity.