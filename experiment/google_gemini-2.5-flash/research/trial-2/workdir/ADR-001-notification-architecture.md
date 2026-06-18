# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system, integrated synchronously within the HTTP request cycle of our Python/Flask monolith, is experiencing significant scaling issues. These include request timeouts, silent failures for critical notifications, cascading failures due to slow external services, and a lack of delivery guarantees (especially for billing-critical events).

Our SaaS project management platform serves 85,000 monthly active users, generating approximately 2 million tasks per month with peak loads of ~500 requests/second. The existing infrastructure includes a PostgreSQL database, 4 web servers, Nginx, and Redis used for session management and rate limiting.

We need to decouple notification processing to be asynchronous, implement retry mechanisms with exponential backoff, guarantee at-least-once delivery for all notifications, and exactly-once delivery for billing-critical events. The new system must support future real-time WebSocket push notifications and scale to 10x current traffic.

Key constraints include a small engineering team of 6 (no dedicated infrastructure engineer and no Kafka experience), a tight 2-week timeline for initial value delivery, and a modest budget precluding expensive managed services like Confluent Cloud.

## Decision
We choose **Redis Streams** for the notification subsystem.

This decision is primarily driven by the team's existing familiarity with Redis, the modest budget, and the requirement for rapid initial delivery. Redis Streams provides the core messaging capabilities needed, including ordered append-only logs, consumer groups, and message retention, which can be leveraged to achieve the required delivery guarantees. The existing Redis instance can be extended, minimizing operational overhead and setup time.

## Consequences

### Pros
*   **Reduced Operational Complexity**: Leveraging the existing Redis instance significantly reduces the operational burden. The team is already familiar with Redis, eliminating the need to learn and manage a completely new distributed system like Kafka. This aligns with the constraint of "no dedicated infrastructure engineer" and the 2-week setup/migration timeline.
*   **Fast Setup and Integration**: Redis Streams can be quickly integrated into the Python/Flask application. The learning curve for Redis Streams for a team already using Redis is much lower than for Kafka.
*   **At-Least-Once Delivery**: Redis Streams, with consumer groups, naturally supports at-least-once delivery. Consumers acknowledge messages, and unacknowledged messages are delivered to other consumers in the group upon failure.
*   **Exactly-Once Semantics (Feasible)**: While not inherent "exactly-once" in the same way a distributed transaction manager would provide, it is feasible to achieve idempotent processing for billing notifications by combining Redis Streams consumer groups with transaction IDs or unique message IDs and ensuring idempotency at the downstream service. This satisfies the "exactly-once where feasible" requirement for critical events.
*   **Cost-Effective**: Utilizing the existing Redis infrastructure is more budget-friendly than introducing a new distributed system that might require dedicated managed services for stability and scale, which the budget currently does not allow.
*   **Future-Proofing for WebSockets**: Redis Pub/Sub (which integrates well with Redis Streams) is a strong candidate for building real-time WebSocket push notifications, aligning with the 2-quarter roadmap item.

### Cons
*   **Scaling Limitations Compared to Kafka**: While Redis Streams can handle significant load, it may not scale to the extreme throughput levels or handle the massive historical data retention that Kafka is designed for. For the initial 10x growth target, it should suffice, but beyond that, a re-evaluation might be necessary.
*   **Less Mature Ecosystem for Complex Stream Processing**: Kafka has a richer ecosystem for advanced stream processing (e.g., Kafka Streams, ksqlDB). Redis Streams has more basic stream processing capabilities, which may require more custom application-level logic for complex scenarios.
*   **Limited Long-Term Data Retention**: Redis is primarily an in-memory data store, and while Redis Streams supports persistence, long-term retention of massive notification histories would require careful planning around disk space and memory usage, potentially pushing against budget constraints or operational complexity limits. Kafka is inherently designed for long-term, high-volume data retention.
*   **Complexity for Exactly-Once**: Achieving robust exactly-once semantics still requires careful application-level design for idempotency in the consumer, as Redis Streams itself provides at-least-once. Kafka's transactional API offers more built-in support for exactly-once guarantees across producers and consumers within the Kafka ecosystem, though this still requires careful implementation.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its robust features tailored for high-throughput, fault-tolerant, and scalable distributed streaming. It provides strong ordering guarantees, advanced consumer group management, and a rich ecosystem for stream processing and analytics. Kafka is excellent for scenarios requiring long-term data retention and high fan-out.

However, it was rejected due to several critical constraints:
*   **Lack of Team Expertise**: The engineering team has no prior Kafka experience. Introducing Kafka would necessitate a significant learning curve, violating the "2 weeks of setup/migration work before delivering value" constraint.
*   **Operational Overhead**: Kafka is a complex distributed system to operate and manage, especially without a dedicated infrastructure engineer. This would divert critical engineering resources from product development to infrastructure management.
*   **Budget Constraints**: While self-hosting Kafka is an option, it requires considerable expertise to set up for high availability and performance. Managed Kafka services (like Confluent Cloud) that simplify operations are currently outside the "modest budget" constraint at full scale.
*   **Initial Value Delivery Timeline**: The time required to set up, integrate, and stabilize Kafka, given the team's inexperience, would likely exceed the aggressive 2-week timeline for initial value delivery.