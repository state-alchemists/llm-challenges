**Title**: ADR-001-Notification-Architecture
**Status**: Proposed

**Context**
The existing notification module within the Python/Flask monolith synchronously handles emails and webhooks for task updates, assignments, and completions. This design has led to:
1.  **Performance issues**: Request timeouts and high latency (averaging 800ms, spiking to 8s) due to blocking HTTP requests during notification sending.
2.  **Reliability problems**: Silent failures for notifications when external services (email providers, webhook endpoints) are unavailable, with no retry mechanism or dead-letter queue.
3.  **Stability risks**: Cascading failures from slow external services, leading to connection pool exhaustion and impacting unrelated features.
4.  **Lack of delivery guarantees**: No at-least-once or exactly-once semantics for critical billing-related notifications.

The project requires decoupling notifications for asynchronous processing, supporting retry with exponential backoff, guaranteeing at-least-once delivery (exactly-once for billing events), enabling real-time WebSocket push notifications within two quarters, and scaling to 10x traffic growth.

Constraints include a 6-person engineering team (3 senior, 3 mid-level) with no dedicated infrastructure engineer. Redis is already in production for session storage and rate limiting. The team has no prior Kafka experience. The solution must deliver value within two weeks of setup/migration, operate within a modest budget (precluding full-scale managed Confluent Cloud), and maintain exactly-once semantics for billing notifications.

**Decision**
We will adopt **Redis Streams** for the notification subsystem. This decision is primarily driven by the team's existing familiarity with Redis, the operational simplicity of Redis Streams, and the ability to meet critical requirements within the given time and budget constraints.

**Consequences**

**Positive**:
*   **Reduced operational overhead**: Leveraging existing Redis infrastructure and team familiarity lowers the learning curve and operational burden significantly. No new distributed system to manage immediately.
*   **Fast time-to-value**: Redis Streams can be integrated quickly, potentially meeting the 2-week value delivery constraint due to its lightweight nature and `redis-py` support.
*   **Asynchronous processing**: Decouples notification sending from the HTTP request cycle, improving backend latency and overall system responsiveness.
*   **At-least-once delivery**: Consumer groups in Redis Streams provide built-in mechanisms for at-least-once delivery and handling consumer failures.
*   **Exactly-once semantics**: Achievable for billing notifications through idempotent processing on the consumer side, combined with Redis Stream's unique message IDs.
*   **Real-time capabilities**: Redis's low-latency nature is well-suited for future WebSocket push notifications.
*   **Modest resource usage**: Redis Streams are memory-efficient, reducing infrastructure costs compared to a full-blown Kafka cluster.

**Negative**:
*   **Limited long-term message retention**: While configurable, Redis Streams are primarily designed for bounded backlogs. Long-term archival requires external storage.
*   **Scalability for extreme throughput**: While Redis Streams can handle significant load, it may not scale to the *extreme* message volumes that a dedicated Kafka cluster can, potentially requiring future re-evaluation beyond the 10x target.
*   **Fewer advanced features**: Lacks some of Kafka's advanced features like schema registry, stream processing frameworks (Kafka Streams/ksqlDB), or a dedicated ecosystem for complex event processing out of the box.
*   **Operational complexity for sharding**: Scaling Redis Streams for very high throughput or large data volumes might eventually require manual sharding or a robust Redis Cluster setup, adding operational complexity.

**Alternatives Considered**

*   **Apache Kafka**: Kafka offers robust high-throughput, horizontally scalable message queuing with strong ordering guarantees, configurable long-term message retention, and a mature ecosystem for stream processing. However, it was rejected due to:
    *   **High operational complexity**: Requires significant expertise for setup, configuration, monitoring, and scaling a Kafka cluster. This is a major concern for a 6-person team with no dedicated infrastructure engineer and no prior Kafka experience.
    *   **Budget constraints**: Managed Kafka services like Confluent Cloud are expensive at scale, and self-hosting would add substantial operational burden and cost.
    *   **Time-to-value**: The learning curve and setup time for Kafka would likely exceed the 2-week constraint for delivering initial value.
    *   **Overkill for initial needs**: While Kafka offers superior scalability for extreme volumes, Redis Streams can adequately meet the immediate 10x growth target without introducing the overhead of a new, complex distributed system. The advanced features of Kafka are not immediately critical and can be considered if/when Redis Streams reaches its limits.