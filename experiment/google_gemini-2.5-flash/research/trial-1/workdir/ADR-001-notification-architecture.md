# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform currently handles notifications (emails, webhooks) synchronously within the HTTP request cycle. With 85,000 monthly active users and ~2M tasks created per month, this synchronous approach has led to:
1.  **Request timeouts**: Latency spikes to 8s during peak hours, blocking responses.
2.  **Silent failures**: Notifications are dropped if external services are unavailable, with no retry mechanism.
3.  **Cascading failures**: Slow webhook endpoints have caused connection pool exhaustion.
4.  **No delivery guarantees**: Billing-critical notifications lack at-least-once or exactly-once delivery guarantees.

We need to re-architect the notification subsystem to:
*   Decouple notification processing from the HTTP request cycle for asynchronous handling.
*   Implement retry mechanisms with exponential backoff.
*   Guarantee at-least-once delivery for all notifications, and strictly exactly-once delivery for billing-critical events.
*   Support future real-time WebSocket push notifications.
*   Scale to 10x current traffic (5000 req/s peak) without major re-architecture.

Constraints:
*   **Team Size/Expertise**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer, and no prior Kafka experience.
*   **Existing Infrastructure**: Redis is already deployed and used for session management and rate limiting.
*   **Time to Value**: Must deliver value within 2 weeks of setup/migration.
*   **Budget**: Modest, ruling out expensive fully managed Kafka solutions.

## Decision
We choose **Redis Streams** for the notification subsystem.

This decision prioritizes leveraging existing infrastructure and team familiarity, minimizing operational overhead, and meeting the strict 2-week time-to-value constraint. While Apache Kafka offers superior guarantees and scalability at extreme volumes, its operational complexity and the team's lack of experience present a significant initial barrier that would exceed our immediate constraints.

Redis Streams provides a robust, ordered, and persistent log suitable for message queuing. Its consumer group functionality facilitates scalable message processing, and its `XACK` command allows for explicit acknowledgment, enabling at-least-once delivery. For billing-critical notifications requiring exactly-once semantics, we will implement idempotent consumers and leverage unique message IDs within the application logic, ensuring that duplicate processing does not lead to incorrect outcomes.

## Consequences
### Pros
*   **Leverages Existing Infrastructure & Expertise**: Reduces the learning curve and operational burden since Redis is already in production and the team has familiarity with it. This directly addresses the constraint of no dedicated infrastructure engineer and limited Kafka experience.
*   **Rapid Development & Deployment**: Integration with Redis Streams is relatively straightforward, making it feasible to meet the 2-week setup/migration timeline and quickly deliver value by decoupling notifications.
*   **Lower Operational Complexity**: Self-managing Redis is less complex than self-managing a Kafka cluster, which requires expertise in ZooKeeper/Kraft, broker management, topic partitioning, and replication. This aligns with our modest budget and lack of dedicated infra staff.
*   **At-Least-Once Delivery**: Redis Streams naturally supports at-least-once delivery through consumer groups and explicit message acknowledgment (`XACK`), addressing silent failures and providing retries.
*   **Future WebSocket Support**: The ordered log nature of Redis Streams makes it suitable for feeding real-time data to WebSocket servers for push notifications.

### Cons
*   **Exactly-Once Semantics**: While achievable for billing-critical events, it requires more careful application-level design and implementation of idempotent consumers, rather than relying on more built-in primitives available in Kafka. This increases development complexity for critical paths.
*   **Scalability Limitations**: While sufficient for 10x growth from current metrics, Redis Streams may not scale as effortlessly or to the same extreme throughput as Kafka for very high-volume, global-scale systems without careful partitioning and instance management. This could be a concern for future growth beyond 10x.
*   **Message Retention Impact**: Storing messages in Redis Streams consumes memory. While configurable, long retention periods for very high volumes could lead to increased memory usage and potentially higher Redis instance costs or performance degradation if not managed.
*   **Ecosystem Maturity**: The surrounding ecosystem (monitoring, stream processing frameworks, connectors) is less mature and extensive compared to Kafka.

## Alternatives Considered
### Apache Kafka
Apache Kafka was considered due to its industry-leading capabilities for high-throughput, fault-tolerant, and scalable stream processing. It offers robust consumer group rebalancing, configurable message retention, strong ordering guarantees within partitions, and powerful primitives for achieving exactly-once semantics across distributed systems (e.g., using transactions and idempotent producers/consumers).

However, we rejected Kafka primarily due to the following constraints:
*   **Operational Complexity**: Deploying and managing a Kafka cluster (especially self-hosted, given budget constraints preclude fully managed Confluent Cloud) is significantly more complex than managing Redis. This would place a heavy burden on our 6-person engineering team, which lacks a dedicated infrastructure engineer and existing Kafka experience. The learning curve for the team would be steep.
*   **Setup/Migration Time**: Integrating and deploying Kafka, especially without prior experience, would almost certainly exceed the 2-week time-to-value constraint. Setting up a production-ready Kafka cluster with monitoring, replication, and disaster recovery would be a multi-week, if not multi-month, effort.
*   **Budget**: While open-source Kafka is free, the operational cost (engineer time, potential for incidents) and the need for more powerful instances to run Kafka brokers would likely exceed our modest budget for this phase, particularly if we opted for a partially managed solution.

While Kafka offers a more "complete" solution for advanced streaming requirements and simpler exactly-once semantics at scale, the immediate practical constraints of team expertise, time, and budget make it an unsuitable choice for this project phase. We opt for a solution that provides immediate relief and addresses critical problems without introducing overwhelming operational complexity.
