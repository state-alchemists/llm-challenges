# ADR-001: Notification Subsystem Architecture Decision

## Status
Proposed

## Context
The existing notification module within our Python/Flask monolith synchronously sends emails and webhooks, leading to significant performance issues, unhandled failures, and a lack of delivery guarantees. As user activity (85,000 MAU, ~2M tasks/month, 500 req/s peak) has grown, this has resulted in:
*   **Request timeouts**: Notifications block HTTP responses, causing latencies up to 8 seconds.
*   **Silent failures**: No retries or dead-letter queue for failed notifications (e.g., email provider downtime).
*   **Cascading failures**: Slow webhook endpoints have exhausted connection pools, impacting unrelated features.
*   **No delivery guarantees**: Critical billing notifications (e.g., "trial expired", "payment failed") lack at-least-once or exactly-once semantics.

To address these issues, we need to decouple notifications from the HTTP request cycle, implement async processing with retry logic, guarantee at-least-once delivery for all events, and achieve exactly-once processing for billing-critical notifications. The new architecture must also support 10x traffic growth and integrate real-time WebSocket push notifications within two quarters.

Our engineering team consists of 6 people (3 senior, 3 mid-level), with no dedicated infrastructure engineer. We currently use Redis for session storage and rate limiting, but have no prior experience with Kafka. The solution must provide initial value within two weeks and operate within a modest budget, precluding expensive managed Kafka solutions at full scale.

## Decision
We will implement the notification subsystem using **Redis Streams**.

This decision is driven by a strong alignment with our team's capabilities, existing infrastructure, and immediate time-to-value constraints, while still meeting the scalability and delivery guarantee requirements for the foreseeable future.

### Justification:
1.  **Operational Simplicity & Team Familiarity**: We already operate Redis in production. Integrating Redis Streams leverages existing operational knowledge and tooling, significantly reducing the learning curve and operational burden on our small team (no dedicated infrastructure engineer). Kafka, while powerful, introduces a completely new distributed system with higher operational complexity, requiring specialized knowledge for setup, monitoring, and troubleshooting that our team currently lacks and would take considerable time to acquire.
2.  **Rapid Time-to-Value**: Given the "must not require more than 2 weeks of setup/migration work before delivering value" constraint, Redis Streams offers a much faster path to implementation. It's a feature of an existing service, avoiding the overhead of deploying and configuring a new distributed system like Kafka. Initial decoupling, async processing, and basic retry logic can be implemented quickly.
3.  **Cost-Effectiveness**: By using our existing Redis infrastructure, we avoid the immediate capital expenditure and ongoing operational costs associated with setting up and maintaining a Kafka cluster or subscribing to a managed Kafka service (e.g., Confluent Cloud is explicitly out of budget at full scale). Redis Streams scales horizontally by adding more Redis instances, a familiar scaling pattern for the team.
4.  **Sufficient Feature Set for Current & Future Needs**:
    *   **Asynchronous Processing**: Redis Streams naturally decouples producers and consumers.
    *   **At-Least-Once Delivery**: Consumer Groups in Redis Streams ensure that each message is delivered to at least one consumer in the group, and messages are only marked as processed after explicit acknowledgment (`XACK`).
    *   **Exactly-Once Semantics (Feasible)**: While not native "exactly-once" in the same way some Kafka setups can achieve with transaction coordinators, "effectively exactly-once" processing for critical billing notifications can be implemented by making consumers idempotent and storing processed message IDs in PostgreSQL. This approach is well-understood and achievable with Redis Streams.
    *   **Retry with Exponential Backoff & DLQ**: Redis Streams' consumer groups, combined with the `XPENDING` command and custom consumer logic, allow for robust retry mechanisms. A separate Redis Stream can serve as a Dead Letter Queue (DLQ) for messages that fail after all retries.
    *   **Traffic Growth (10x)**: Redis Streams can handle our projected 10x traffic growth (5000 req/s equivalent) by scaling Redis horizontally. Benchmarks show Redis Streams can achieve high throughput (hundreds of thousands of messages/second on a single instance), which is more than sufficient for our current and anticipated notification volume.
    *   **WebSocket Push Notifications**: Redis's existing Pub/Sub capabilities, combined with Streams, make it an excellent choice for future real-time WebSocket integration. Streams can serve as the durable log for events, while Pub/Sub can push updates to connected WebSocket clients.
    *   **Message Retention**: Configurable message retention (e.g., by size or time) within the stream allows us to manage memory usage while retaining a history of notifications for debugging or replay if needed.
    *   **Ordering Guarantees**: Redis Streams provide strict ordering within a single stream, which is important for maintaining the sequence of notification events related to a user or task.

## Consequences

### Pros
*   **Reduced Operational Overhead**: Leverages existing Redis infrastructure and team knowledge, minimizing setup, maintenance, and monitoring complexity.
*   **Faster Development Cycle**: Quicker to implement and iterate on new notification features due to familiarity with Redis and its client libraries.
*   **Cost Savings**: Avoids the expense of new infrastructure or managed services for a dedicated message broker.
*   **Scalability**: Redis Streams can scale to handle 10x current traffic (5000 req/s equivalent) by horizontal scaling of Redis.
*   **Feature Completeness**: Supports async processing, retry mechanisms, DLQ patterns, at-least-once, and effectively exactly-once semantics.
*   **Future-Proofing**: Well-suited for integrating real-time WebSocket push notifications later.

### Cons
*   **Less Mature Ecosystem for Advanced Features**: While sufficient, the ecosystem around Redis Streams (e.g., monitoring, connectors, stream processing frameworks) is not as mature or extensive as Kafka's. This might require more custom development for complex scenarios.
*   **Limited Geo-Replication & Multi-Region**: Redis's built-in replication is primarily for high availability within a region. Advanced geo-replication for distributed streams across multiple regions is more complex to set up and manage compared to Kafka.
*   **Potential for Operator Error**: Misconfiguration of Redis Streams (e.g., unbounded stream size, incorrect `XACK` usage) could lead to memory issues or message reprocessing if not carefully managed. Requires careful design of consumer logic.
*   **Durability and Persistence**: While Redis Streams are persistent, a single Redis instance failure (without proper replication and snapshotting) could lead to data loss if not configured correctly. This risk is mitigated by existing Redis deployment practices and replication.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-standard status, high throughput, strong durability guarantees, and mature ecosystem. However, it was rejected for the following reasons:

*   **High Operational Complexity**: Kafka is a distributed system with significant operational overhead. It requires specialized knowledge for deployment, configuration, monitoring, and maintenance (e.g., ZooKeeper/Kraft, brokers, topics, partitions, consumer groups, offsets). Our team of 6 engineers, with no dedicated infrastructure engineer and no Kafka experience, would face a steep learning curve and substantial time investment to become proficient. This directly conflicts with the constraint of "not require more than 2 weeks of setup/migration work before delivering value."
*   **Cost**: Running a self-managed Kafka cluster at scale requires considerable resources, and managed services like Confluent Cloud are explicitly "out of budget at full scale today." Even initial setup costs for a robust Kafka deployment would likely exceed our modest budget.
*   **Time-to-Value**: The initial setup, learning, and integration time for Kafka would far exceed the two-week constraint for delivering value.
*   **Overkill for Current Scale**: While Kafka excels at massive scale (millions of events/second), our current and projected 10x growth (5000 req/s equivalent) can be comfortably handled by Redis Streams without the added complexity. Kafka's full capabilities are not strictly necessary for our immediate needs, making its adoption an over-engineering choice at this stage.
*   **Impedance Mismatch with Existing Stack**: Introducing Kafka would mean managing a completely new technology stack component, whereas Redis Streams extends our existing Redis usage.
