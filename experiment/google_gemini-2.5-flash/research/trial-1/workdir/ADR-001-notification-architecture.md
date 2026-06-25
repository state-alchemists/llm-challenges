# ADR-001: Notification Subsystem Architecture Decision

## Status
Proposed

## Context
The existing notification module within our Python/Flask monolith synchronously sends emails and webhooks, leading to severe issues: request timeouts (average 800ms, spikes to 8s), silent failures with no retries, and cascading failures due to connection pool exhaustion. Billing-critical notifications lack delivery guarantees.

Our scaling targets require decoupling notifications from the HTTP request cycle for asynchronous processing, supporting retry with exponential backoff, guaranteeing at-least-once delivery for billing events (and exactly-once where feasible), and enabling real-time WebSocket push notifications within two quarters. The system must handle 10x traffic growth without a major re-architecture.

Key constraints include: a 6-person engineering team (no dedicated infrastructure engineer), existing Redis in production, no current Kafka experience, a maximum of 2 weeks for setup/migration to deliver initial value, a modest budget precluding full-scale managed Confluent Cloud, and the critical need for exactly-once semantics for billing notifications.

## Decision
We choose **Redis Streams** as the foundation for the new notification subsystem.

This decision is driven primarily by the existing operational familiarity with Redis, the modest engineering team size, and the tight timeline for initial value delivery. While Kafka offers superior scalability for extreme throughput and a richer ecosystem for complex data pipelines, its operational overhead and the team's lack of experience present a significant barrier to meeting the "2 weeks to value" constraint. Redis Streams, leveraging an already deployed and understood technology, allows for rapid implementation and iteration while still addressing the immediate critical needs for asynchronous processing, retry mechanisms, and delivery guarantees. The ability to achieve exactly-once processing with Redis Streams through idempotent consumer logic, combined with its native support for consumer groups and configurable message retention, makes it a viable choice for our current scale and growth trajectory, especially for billing-critical events.

## Consequences

### Pros
*   **Reduced Operational Complexity**: Leveraging an existing Redis instance significantly lowers the operational burden compared to introducing a new distributed system like Kafka. The team already understands Redis monitoring, backups, and scaling basics.
*   **Faster Time to Value**: With existing Redis infrastructure and team familiarity, initial setup and integration are expected to be much faster, aligning with the "2 weeks to value" constraint.
*   **Native Redis Ecosystem**: Seamless integration with other Redis features (e.g., Pub/Sub for WebSocket push notifications, Redis Keyspace Notifications for triggering other events) can simplify future feature development within the Redis ecosystem.
*   **At-least-once and Exactly-once Semantics**: Redis Streams support consumer groups that allow messages to be processed at-least-once. For billing-critical notifications, exactly-once semantics can be achieved by implementing idempotent consumer logic, leveraging Redis's atomic operations or external transaction IDs.
*   **Decoupling and Resilience**: Provides asynchronous processing, effectively decoupling notification sending from the HTTP request cycle, eliminating timeouts and cascading failures.
*   **Modest Resource Footprint**: Redis Streams are generally more lightweight than a full Kafka cluster, fitting within the modest budget constraint.

### Cons
*   **Scalability Limits for Extreme Throughput**: While sufficient for our current 10x growth target, Redis Streams may eventually hit scaling limitations compared to Kafka's massive throughput capabilities for very high message volumes (e.g., 100x+ growth or millions of messages per second) without significant sharding and cluster management efforts.
*   **Limited Ecosystem**: Kafka has a richer ecosystem of connectors, stream processing frameworks (e.g., Flink, Spark Streaming), and monitoring tools designed for large-scale data pipelines. Redis Streams' ecosystem is simpler, requiring more custom development for complex stream processing needs.
*   **Message Retention Management**: While configurable, managing long-term message retention for auditing or historical replay might require more manual effort or integration with external storage compared to Kafka's design for durable logs.
*   **Potential for Redis Congestion**: Placing notification streams on the same Redis instance used for sessions and rate limiting introduces a single point of congestion risk. Proper resource isolation and monitoring will be crucial. This may necessitate dedicated Redis instances as traffic grows.

## Alternatives Considered

### Apache Kafka
Apache Kafka was considered due to its industry-leading performance, high throughput, and robust features for distributed streaming. Its strengths include:
*   **Extreme Scalability**: Designed for petabytes of data and millions of messages per second, easily handling our 10x traffic growth and beyond without re-architecture.
*   **Durability and Retention**: Excellent message durability with configurable retention policies, making it ideal for auditing and historical data replay.
*   **Rich Ecosystem**: Extensive ecosystem with Kafka Connect for integration, Kafka Streams for stream processing, and mature monitoring tools.
*   **Strong Delivery Guarantees**: Native support for at-least-once, and exactly-once semantics through transactional producers and consumers, simplifying implementation for critical notifications.

However, Kafka was rejected primarily due to the **operational complexity** and the **team's lack of experience**. Introducing and managing a Kafka cluster (even a self-hosted one, given the budget constraints) requires specialized infrastructure knowledge that our 6-person engineering team currently lacks. The estimated ramp-up time for deployment, configuration, monitoring, and troubleshooting would far exceed the "2 weeks of setup/migration work before delivering value" constraint. While managed Kafka offerings exist, they were deemed too expensive for our "modest budget" at scale today. The learning curve and initial investment in operational expertise would divert significant resources from product development, making it a non-viable option given our immediate constraints.