# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification module within our Python/Flask monolith synchronously sends emails and webhooks upon task updates. This design has led to critical issues:
1.  **Request Timeouts**: Notification sending blocks the HTTP request cycle, causing average latencies of 800ms and spikes up to 8 seconds during peak loads (~500 req/s).
2.  **Silent Failures**: Notifications are dropped without retry or dead-letter queuing if external services (email providers, webhook endpoints) are unavailable.
3.  **Cascading Failures**: External service slowness has previously led to connection pool exhaustion and outages of unrelated features.
4.  **No Delivery Guarantees**: There are no guarantees for critical billing-related notifications ("trial expired", "payment failed") which require at-least-once, and ideally exactly-once, delivery.

To address these problems and support future growth, we need to decouple notifications from the request cycle, implement asynchronous processing, support retry mechanisms, ensure at-least-once delivery for billing events (with exactly-once as a strong preference), and prepare for 10x traffic growth and real-time WebSocket push notifications within two quarters.

**Key Constraints:**
*   **Team Size**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure team.
*   **Existing Infrastructure**: We currently use Redis for session storage and rate limiting. No prior Kafka experience.
*   **Time to Value**: Must deliver value within 2 weeks of setup/migration.
*   **Budget**: Modest, ruling out expensive managed Kafka solutions at full scale.
*   **Delivery Guarantee**: Must maintain exactly-once semantics for billing notifications.

## Decision
We choose **Redis Streams** for the new notification subsystem.

While Apache Kafka offers robust features for large-scale distributed messaging, its operational complexity, lack of existing team expertise, and the tight timeframe for initial delivery make it less suitable for our current team and constraints. Redis Streams, leveraging our existing Redis infrastructure and team familiarity, provides a significantly lower barrier to entry and faster time to value, while still meeting most of our scaling targets and delivery guarantees with careful implementation.

For exactly-once semantics required for billing notifications, we will implement idempotent consumers. This means consumer logic will be designed to process messages multiple times without adverse effects. Transactions for critical operations will be handled at the application layer, ensuring that even if a message is re-delivered, the resulting state change is applied only once.

## Consequences

### Pros of Redis Streams:
*   **Lower Operational Complexity**: Redis is already in production and familiar to the team, drastically reducing the learning curve and operational burden compared to Kafka, which often requires dedicated SRE resources.
*   **Faster Time to Value**: Setup and integration will be significantly quicker, aligning with the "2 weeks of setup/migration" constraint.
*   **Leverages Existing Infrastructure**: Utilizes the Redis instances we already operate, optimizing resource usage and simplifying our technology stack.
*   **Good Throughput for Current Needs**: Redis Streams can handle high throughput (tens of thousands of messages/second on a single instance), sufficient for our current ~500 req/s peak and initial 10x growth target.
*   **Consumer Groups**: Provides built-in consumer group functionality for scalable and reliable message consumption, similar to Kafka.
*   **Ordering Guarantees**: Guarantees order within a stream, which is crucial for event sequencing.
*   **Message Retention**: Configurable stream trimming (max length) allows us to manage memory usage while retaining a history of events.
*   **Real-time Capabilities**: Redis is well-suited for real-time applications, making the future integration of WebSocket push notifications more straightforward.

### Cons of Redis Streams:
*   **Exactly-Once Semantics**: Achieving strict exactly-once semantics requires more effort at the application level (idempotent consumers, transaction management) compared to Kafka's native transactional API. This will add complexity to critical billing notification consumers.
*   **Scalability Limitations**: While capable of high throughput, a single Redis instance will eventually hit limitations. Horizontal scaling of Redis Streams (e.g., across multiple Redis clusters or sharded instances) is more complex than Kafka's inherent distributed architecture.
*   **Message Size**: Redis is generally optimized for smaller messages. Very large notification payloads could be less efficient than in Kafka.
*   **Durability**: Redis's persistence options (RDB, AOF) provide durability, but Kafka's append-only log is fundamentally designed for higher data durability and long-term retention across a distributed cluster.

## Alternatives Considered

### Apache Kafka
**Why Rejected:**
*   **High Operational Complexity**: Kafka is a powerful but complex distributed system. Deploying, monitoring, and maintaining a Kafka cluster requires significant expertise, which our 6-person team (without a dedicated infrastructure engineer and no prior Kafka experience) currently lacks. This poses a high risk for stability and increased operational overhead.
*   **Steep Learning Curve**: The team would need substantial time to learn Kafka's ecosystem, concepts (brokers, topics, partitions, Zookeeper/Kraft, consumer groups, offsets, stream processing frameworks), and best practices. This directly conflicts with the "2 weeks of setup/migration" constraint.
*   **Budget Constraints**: While self-hosting Kafka is an option to manage costs, the operational burden would be immense. Managed Kafka services (like Confluent Cloud) would likely exceed our "modest budget" at full scale, making it an unsustainable choice for the long term without significant investment.
*   **Overkill for Initial Needs**: While Kafka's extreme scalability and resilience are attractive for future growth, for our immediate problem and existing traffic patterns, it represents an over-engineered solution that brings significant cost in terms of team resources and complexity. The initial 10x growth target can likely be met by Redis Streams before needing to consider Kafka.

While Kafka offers stronger native support for exactly-once semantics and superior long-term message retention and throughput for massive scale, these benefits are outweighed by the immediate challenges related to team expertise, operational overhead, and project timeline. We believe Redis Streams offers a more practical, achievable, and cost-effective solution for our current stage, with a clear path to scale if and when its limitations become a bottleneck.
