# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification subsystem, part of a Python/Flask monolith, handles email and webhook notifications synchronously within the HTTP request cycle. This design has led to critical issues:
1.  **Performance Degradation**: Request timeouts and high latency (averaging 800ms, spiking to 8s) due to blocking I/O operations for notification sending.
2.  **Reliability Issues**: Notifications are silently dropped on external service failures (e.g., email provider downtime, slow webhook endpoints), with no retry mechanism or dead-letter queue.
3.  **System Instability**: Cascading failures have occurred where slow external services exhausted connection pools, impacting unrelated parts of the application.
4.  **Lack of Guarantees**: No delivery guarantees, which is problematic for billing-critical notifications requiring at-least-once or exactly-once delivery.

The objective is to decouple notification processing from the main request path, implement robust retry mechanisms, ensure delivery guarantees (at-least-once, exactly-once for critical events), and support future real-time WebSocket notifications. The solution must scale 10x, leverage existing infrastructure where possible, and be implementable within two weeks by a small team (6 engineers, no dedicated infra) with a modest budget. Existing Redis usage is a factor; the team has no prior Kafka experience.

## Decision
We choose **Redis Streams** for the notification subsystem.

While Apache Kafka offers superior capabilities for large-scale, high-throughput data streaming, Redis Streams provides a more pragmatic and efficient solution given our specific constraints, particularly the team's existing familiarity with Redis, the limited operational budget, and the strict two-week setup/migration timeline. The "modest budget" constraint directly rules out managed Kafka services at full scale, making self-hosted Kafka an operational burden for a team without dedicated infrastructure engineers. Redis Streams can meet the required delivery guarantees (at-least-once, and exactly-once processing with idempotent consumers) and will facilitate the planned real-time WebSocket notifications. Its operational simplicity and low overhead align well with the team's capacity.

## Consequences

### Pros of Redis Streams:
*   **Operational Simplicity**: As we already operate Redis, adding Streams functionality requires minimal new operational overhead. This significantly reduces the learning curve and management burden for the small engineering team with no dedicated infrastructure specialist.
*   **Fast Time to Value**: Leveraging an existing Redis instance and familiar technology means the initial setup and migration can realistically be achieved within the two-week constraint.
*   **At-Least-Once Delivery**: Redis Streams, with consumer groups, provides at-least-once delivery semantics, which is crucial for billing-critical notifications. Dead-letter queues can be implemented with a separate stream for failed messages.
*   **Exactly-Once Processing**: While Redis Streams natively offers at-least-once delivery, exactly-once *processing* can be achieved by making consumers idempotent, a common pattern that aligns with the "exactly-once where feasible" requirement for billing events.
*   **Real-time Capabilities**: Redis's pub/sub and Streams features are well-suited for the future integration of real-time WebSocket push notifications, providing a unified solution for both async and real-time messaging.
*   **Cost-Effective**: Utilizing our existing Redis infrastructure keeps costs low, aligning with the modest budget constraint.

### Cons of Redis Streams:
*   **Lower Throughput/Scalability vs. Kafka**: For extremely high throughput (millions of messages per second) or petabyte-scale data retention, Kafka is superior. However, Redis Streams can comfortably handle the current ~2M messages/month and projected 10x growth.
*   **Less Mature Ecosystem**: While Redis Streams is robust, its ecosystem (monitoring, connectors, stream processing frameworks) is less mature and extensive than Kafka's. This may require more custom development for advanced use cases.
*   **Limited Message Retention**: Redis is primarily an in-memory store; while Streams support disk persistence, it's not designed for indefinite, large-scale message retention like Kafka. This necessitates careful planning for retention policies or offloading older data if long-term history is required.
*   **Complexity for Advanced Features**: Implementing features like schema evolution or complex stream transformations might be more involved compared to Kafka's native tooling.

## Alternatives Considered

### Apache Kafka
**Reason for Rejection**:
Kafka is a powerful, distributed streaming platform offering high throughput, long-term message retention, and a mature ecosystem for complex data pipelines. It natively provides strong ordering guarantees, robust consumer groups, and support for exactly-once semantics via transactions. However, given our specific constraints, Kafka presents significant challenges:
*   **Operational Complexity**: The engineering team has no dedicated infrastructure engineer and no prior Kafka experience. Setting up, operating, and maintaining a self-hosted Kafka cluster (including ZooKeeper/Kraft, brokers, and potentially Schema Registry) would require substantial time and specialized knowledge, far exceeding the two-week setup/migration limit.
*   **Cost**: While open-source Kafka is free, running it at scale often entails significant operational costs (e.g., cloud VMs, storage, monitoring). Managed services like Confluent Cloud, which would mitigate operational burden, are explicitly out of budget for full scale.
*   **Time to Value**: The steep learning curve and operational complexity would severely delay initial value delivery, failing the "must not require more than 2 weeks" constraint.
*   **Overkill for Initial Needs**: While Kafka's capabilities are vast, they are largely beyond the immediate needs of handling ~2M notifications/month with 10x growth. The overhead and complexity would outweigh the benefits for our current scale.
