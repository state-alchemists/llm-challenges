# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification subsystem, part of a Python/Flask monolith, handles emails and webhooks synchronously within the HTTP request cycle. This has led to critical issues including request timeouts (average 800ms, peaks to 8s), silent failures with no retry mechanism, cascading failures due to slow external dependencies, and a complete lack of delivery guarantees, especially for billing-critical events which require exactly-once processing.

Our project management platform serves 85,000 monthly active users, generates ~2M tasks/month, and experiences peak loads of ~500 req/s. We need to decouple notifications for asynchronous processing, implement retry with exponential backoff, guarantee at-least-once (and ideally exactly-once) delivery, and prepare for real-time WebSocket push notifications within two quarters. The solution must scale to 10x current traffic without a complete re-architecture.

Key constraints:
*   **Team Size**: 6 engineers (3 senior, 3 mid-level), with no dedicated infrastructure engineer.
*   **Existing Infrastructure**: Redis is already in production for session management and rate limiting.
*   **Team Experience**: No prior Kafka experience.
*   **Time to Value**: Must deliver value within 2 weeks of setup/migration.
*   **Budget**: Modest, precluding fully managed Kafka solutions like Confluent Cloud at full scale.
*   **Critical Requirement**: Must ensure exactly-once semantics for billing notifications.

## Decision
We recommend implementing the new notification subsystem using **Redis Streams**.

Redis Streams offers a pragmatic and efficient solution that aligns with our team's capabilities and project constraints. It provides native support for persistent, ordered message queues, consumer groups for scalable message processing, and is well-suited for implementing both at-least-once and exactly-once delivery semantics with idempotent consumers and proper acknowledgment. Crucially, leveraging our existing Redis infrastructure and team expertise significantly reduces the operational overhead, learning curve, and time to value compared to introducing a new distributed system.

## Consequences

### Pros
*   **Low Operational Complexity**: We already operate Redis in production, meaning existing monitoring, backup, and scaling knowledge can be directly applied. This is vital for a team without a dedicated infrastructure engineer.
*   **Fast Time to Value**: Integration with existing Redis instances is straightforward, allowing us to quickly decouple notifications and start addressing critical issues within the 2-week constraint.
*   **Sufficient Performance**: Redis Streams provides high throughput that is more than adequate for our current and 10x projected traffic, easily handling ~5,000 req/s.
*   **Strong Ordering Guarantees**: Messages within a stream are strictly ordered, which is essential for preserving the sequence of events (e.g., task updates).
*   **Reliable Consumer Groups**: Built-in consumer groups enable multiple consumers to process messages collaboratively, track progress, and facilitate automatic re-delivery of unacknowledged messages, directly supporting retry logic and at-least-once delivery.
*   **Exactly-Once Semantics (Achievable)**: With idempotent consumer logic and careful use of Redis Streams' `XACK` within consumer groups, exactly-once processing for billing events can be implemented.
*   **Real-time Capabilities**: Redis's low-latency nature makes it an excellent foundation for future real-time WebSocket push notifications.
*   **Cost-Effective**: Minimal incremental cost since Redis infrastructure is already in place.

### Cons
*   **Scalability for Extreme Throughput**: While sufficient for our 10x target, Redis Streams might not scale as effortlessly as a fully partitioned Kafka cluster for truly astronomical, petabyte-scale data streams or extremely high message fan-out scenarios. However, this is beyond our current and foreseeable needs.
*   **Long-Term Message Retention**: Redis is primarily an in-memory data store, though it supports persistence (RDB/AOF). While configurable, retaining messages for months or years in Redis might be less efficient or cost-effective than Kafka's disk-optimized log architecture for specific use cases (e.g., event sourcing for auditing). For notification history, a separate data store would be more appropriate.
*   **Maturity of Ecosystem**: The ecosystem around Kafka (tooling, connectors, monitoring) is more mature and extensive than for Redis Streams, which is a relatively newer feature. This might mean more bespoke development for certain integrations.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-leading capabilities in high-throughput, fault-tolerant, distributed streaming. Its core strengths include:
*   **Massive Scalability**: Designed to handle trillions of messages per day and petabytes of data.
*   **Long-Term Retention**: Optimized for durable storage of message logs over extended periods.
*   **Robust Ecosystem**: Extensive tooling, connectors, and integration options.
*   **Advanced Features**: Strong support for stream processing frameworks (Kafka Streams, Flink, Spark Streaming).

However, Kafka was rejected primarily due to its high operational complexity and the significant barrier to adoption for our team:
*   **High Operational Overhead**: Setting up, monitoring, and maintaining a Kafka cluster (brokers, Zookeeper/Kraft) requires deep expertise in distributed systems, which our team of 6 engineers lacks ("no dedicated infrastructure engineer"). This would introduce a substantial new operational burden.
*   **Steep Learning Curve**: "No Kafka experience on the team today" means a significant ramp-up time, likely exceeding the "2 weeks of setup/migration" constraint. This would delay critical improvements.
*   **Budget Constraints**: Managed Kafka services like Confluent Cloud are expensive, and our "modest" budget prevents their use "at full scale today." Self-hosting, while cheaper in direct licensing costs, incurs high operational costs in terms of engineering time and effort.
*   **Overkill for Current Needs**: While Kafka's capabilities are immense, they are largely beyond our immediate requirements (10x traffic on 500 req/s is well within Redis Streams' capacity). Introducing such a complex system prematurely would violate the principle of simplicity and efficient resource allocation.