**Title**: ADR-001: Notification Subsystem Architecture Decision
**Status**: Proposed

**Context**:
The existing synchronous notification system in the Python/Flask monolith is causing significant issues including request timeouts, silent failures, cascading system failures, and a lack of delivery guarantees for critical notifications. The system needs to be decoupled, support retries with exponential backoff, ensure at-least-once delivery for all notifications, and exactly-once processing for billing-critical events. The new architecture must also support future WebSocket push notifications and handle 10x traffic growth.

Key constraints include a small engineering team (6 people) with no dedicated infrastructure engineer and no prior Kafka experience. Redis is already in production for caching. The solution must provide value within two weeks and operate within a modest budget, precluding expensive managed Kafka solutions at full scale. 

**Decision**:
We will adopt **Redis Streams** for the notification subsystem.

This decision is driven primarily by the team's existing operational experience with Redis, the immediate need for a solution that delivers value quickly (within two weeks), and the modest budget. Redis Streams provides the core messaging capabilities required—persistent, ordered, and replayable message queues with consumer groups—without introducing a completely new technology stack. This significantly reduces the operational overhead and learning curve for the engineering team, allowing them to focus on application-level logic for retries, DLQs, and idempotent processing.

While Redis Streams might not offer the same raw throughput or advanced enterprise features as Kafka at extreme scale, it adequately meets the immediate scaling target of 10x traffic growth, which translates to a peak of ~5000 req/s. The ability to leverage existing Redis infrastructure and team familiarity makes it the most pragmatic choice for rapid development and deployment given the project constraints. Furthermore, the explicit requirement for "exactly-once semantics for billing notifications" is achievable with Redis Streams by implementing idempotent consumers with external state tracking (e.g., in PostgreSQL), as outlined in the project todos.

**Consequences**:

*   **Pros**:
    *   **Reduced Operational Complexity**: Leverages existing Redis infrastructure and team knowledge, minimizing the learning curve for operations and debugging.
    *   **Rapid Implementation**: Faster setup and migration time, aligning with the "2 weeks to value" constraint.
    *   **Cost-Effective**: Avoids the immediate need for expensive managed Kafka solutions, fitting within the modest budget.
    *   **Strong Feature Set for Requirements**: Provides ordered message queues, consumer groups, persistence, and message replay, which are essential for retries, DLQs, and future WebSocket integration.
    *   **Scalability**: Supports current and 10x projected traffic growth through horizontal scaling of consumers and Redis instances.
    *   **Exactly-once Semantics**: Achievable for billing notifications with careful consumer implementation (idempotency checks against PostgreSQL).

*   **Cons**:
    *   **Less Mature Ecosystem**: Compared to Kafka, the ecosystem around Redis Streams (monitoring tools, connectors, stream processing frameworks) is less mature, potentially requiring more custom development.
    *   **Throughput Limits**: While sufficient for 10x growth, Redis Streams may eventually hit limitations compared to Kafka's higher sustained throughput for truly massive-scale, high-volume data streams.
    *   **Data Retention**: Redis Streams are designed for real-time processing and retention, but long-term archival or highly specific data retention policies might require more manual management than with Kafka.
    *   **Limited Advanced Features**: Lacks some of Kafka's advanced features like complex stream processing (Kafka Streams/KSQL) out-of-the-box, though these can be built atop Redis Streams with custom code.

**Alternatives Considered**:

**Apache Kafka**:
Kafka was considered due to its industry-leading performance, high throughput, robust ordering guarantees, and mature ecosystem for large-scale distributed messaging and stream processing. It natively supports consumer groups, message retention policies, and offers strong primitives for exactly-once semantics.

However, Kafka was rejected primarily due to the "no Kafka experience on the team today" constraint and the "modest budget" limitation preventing the use of fully managed Confluent Cloud. Deploying and operating a self-managed Kafka cluster (especially a highly available one) requires specialized infrastructure expertise and significant operational overhead, which the 6-person engineering team (with no dedicated infrastructure engineer) cannot realistically support within the "2 weeks of setup/migration work" timeframe. The initial learning curve and operational burden would severely impede the project's velocity and risk missing the critical "time to value" requirement. While Kafka is a powerful solution for very high-scale, infrastructure-heavy environments, it introduces too much complexity and cost for the current team and project constraints.