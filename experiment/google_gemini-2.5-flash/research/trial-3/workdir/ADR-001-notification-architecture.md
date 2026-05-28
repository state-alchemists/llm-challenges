# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our existing notification module, responsible for sending emails and webhooks for task-related events, is tightly coupled with the HTTP request cycle. This synchronous processing has led to critical issues:

1.  **Request timeouts and high latency**: Blocking the response cycle for notification sending results in average latencies of 800ms, with spikes up to 8s during peak hours.
2.  **Silent failures and no retries**: If an external service (email provider, webhook endpoint) is unavailable, notifications are silently dropped without any retry mechanism or dead-letter queue.
3.  **Cascading failures**: Slow external webhook endpoints have caused connection pool exhaustion and outages in unrelated parts of the system.
4.  **Lack of delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

To address these issues and support future growth, we need to decouple notification processing, implement retry mechanisms, and ensure reliable delivery guarantees. The system must scale to 10x current traffic (5000 req/s peak) and support real-time WebSocket push notifications within two quarters. Our team consists of 6 engineers with no dedicated infrastructure engineer and no prior Kafka experience. We currently use Redis for session management and rate limiting, and have a modest budget, precluding expensive managed Kafka solutions at full scale initially. The solution must be deployable within two weeks to deliver initial value, and maintain exactly-once semantics for billing notifications.

## Decision
We recommend implementing the notification subsystem using **Redis Streams**.

This decision is primarily driven by the team's existing familiarity with Redis, the modest infrastructure budget, and the rapid time-to-value requirement, while still meeting critical scaling and delivery guarantees for the foreseeable future.

## Consequences

### Pros
*   **Operational Simplicity & Familiarity**: We already operate Redis in production, reducing the operational overhead and learning curve for the existing 6-person engineering team. This directly addresses the constraint of having no dedicated infrastructure engineer and limited Kafka experience. Deployment and management will be significantly simpler than a Kafka cluster. 
*   **Fast Time-to-Value**: Leveraging an existing technology shortens the setup and migration time. We can deliver value within the two-week constraint, crucial for immediately addressing request timeouts and silent failures. 
*   **Cost-Effective**: Running Redis Streams on our existing Redis instances (or a slightly scaled-up version) will be more cost-effective than setting up and managing a Kafka cluster, especially given the modest budget and the inability to afford managed Confluent Cloud. 
*   **Adequate Throughput**: For our current and projected 10x traffic growth (5000 req/s peak), Redis Streams can comfortably handle the message volume. While Kafka can achieve higher throughput, Redis Streams is more than sufficient for our needs and avoids over-engineering. 
*   **Consumer Groups & At-Least-Once Delivery**: Redis Streams natively supports consumer groups, enabling multiple consumers to process messages in parallel and distribute the workload. The `XACK` command, combined with message IDs, allows for at-least-once delivery semantics and robust retry mechanisms, addressing silent failures and providing basic delivery guarantees. 
*   **Exactly-Once Semantics (Feasible)**: While full end-to-end exactly-once semantics are challenging with any distributed system, Redis Streams facilitates achieving it for billing notifications by carefully implementing idempotent consumers. The message ID can be used as a deduplication key in the downstream service, leveraging the transactionality of our PostgreSQL database for state management. This is a pragmatic approach given the constraint and the team's resources. 
*   **Message Retention**: Redis Streams allows for configurable message retention, enabling us to store messages for retry purposes and debugging within a defined window. While not infinite like Kafka, it's sufficient for typical notification retry policies. 
*   **Real-time WebSocket Push Notifications**: Redis's existing Pub/Sub capabilities can be easily integrated with Redis Streams to facilitate real-time WebSocket push notifications, aligning with our future scaling target.

### Cons
*   **Scaling Limitations Compared to Kafka**: While sufficient for 10x current traffic, Redis Streams may hit scalability limits far beyond that, particularly with extremely high message volumes or a requirement for very long-term message retention on disk. Kafka is designed for orders of magnitude higher throughput and petabytes of data retention. This might necessitate a migration to Kafka in the distant future if our growth trajectory exceeds expectations significantly. 
*   **Less Mature Ecosystem for Stream Processing**: Kafka has a more mature and extensive ecosystem for complex stream processing (e.g., Kafka Streams, ksqlDB). While not immediately required, if complex real-time analytics on notification streams become a necessity, Redis Streams might require more custom development. 
*   **Durability and Disk Persistence**: Redis Streams typically store data in memory, with AOF (Append Only File) persistence for durability. While configurable, it's not designed for the same level of cost-effective, long-term, disk-based message retention as Kafka. Large backlogs can consume significant RAM. 
*   **Monitoring and Tooling**: The monitoring and tooling ecosystem for Redis Streams, while improving, is not as mature or comprehensive as that for Apache Kafka. We may need to invest more in custom monitoring and alerting.

## Alternatives Considered

### Apache Kafka

We considered Apache Kafka as a robust, industry-standard solution for distributed streaming. 

**Reasons for Rejection:**
*   **Steep Learning Curve and Operational Complexity**: Our engineering team has no Kafka experience and no dedicated infrastructure engineer. Setting up, configuring, and maintaining a self-managed Kafka cluster (or even a highly available managed one like Confluent Cloud) would introduce significant operational complexity and a steep learning curve, directly violating the "no dedicated infrastructure engineer" and "2 weeks setup/migration" constraints. 
*   **Budget Constraints**: Managed Kafka solutions (like Confluent Cloud) that abstract away much of the operational complexity are expensive at full scale, exceeding our modest budget. Self-hosting Kafka requires significant operational expertise and resources. 
*   **Over-engineering for current needs**: While Kafka excels at massive scale (millions of messages per second, petabytes of data), our current and projected 10x growth can be handled by Redis Streams. Introducing Kafka would be an over-engineered solution for our immediate problems, incurring unnecessary complexity and cost. 
*   **Time-to-Value**: The time required to onboard the team to Kafka, set up the infrastructure, and integrate it into our Flask monolith would likely exceed the two-week constraint for delivering initial value. While Kafka offers strong exactly-once semantics and superior message retention, the trade-offs in operational overhead, cost, and time-to-value make it less suitable for our immediate needs and constraints.