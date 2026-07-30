# ADR-001: Notification Subsystem Architecture

## Title
Notification Subsystem Architecture: Evaluating Kafka vs. Redis Streams

## Status
Proposed

## Context
The existing notification module within our Python/Flask monolith synchronously sends emails and webhooks, leading to several critical issues:
1.  **Request timeouts**: Blocking HTTP requests cause high latency (average 800ms, spikes to 8s).
2.  **Silent failures**: Notifications are dropped if external services are unavailable, with no retry mechanism.
3.  **Cascading failures**: Slow webhook endpoints have caused connection pool exhaustion, impacting other services.
4.  **No delivery guarantees**: Billing-critical notifications lack at-least-once or exactly-once delivery.

Our scaling targets require decoupling notifications for asynchronous processing, supporting retry with exponential backoff, guaranteeing at-least-once delivery (and exactly-once where feasible for billing events), and handling 10x traffic growth without re-architecture. Additionally, we plan to implement real-time WebSocket push notifications within two quarters.

Key constraints:
*   **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
*   **Existing Infrastructure**: We already operate Redis for session storage and rate limiting.
*   **Expertise**: No prior team experience with Apache Kafka.
*   **Timeline**: Must deliver value within 2 weeks of setup/migration.
*   **Budget**: Modest; managed Confluent Cloud at full scale is not affordable.
*   **Criticality**: Exactly-once semantics are required for billing notifications.

## Decision
We choose **Redis Streams** for the new notification subsystem.

This decision prioritizes leveraging existing team expertise and infrastructure, minimizing immediate operational overhead, and meeting the aggressive two-week timeline for initial value delivery. Redis Streams provides the necessary primitives for asynchronous messaging, consumer groups, and message persistence within a technology stack we are already familiar with. While Kafka offers superior capabilities for massive scale and complex stream processing, its operational complexity and the team's lack of experience present significant hurdles that would impede rapid progress and violate our budget and timeline constraints. The "exactly-once" semantics for billing notifications can be achieved with Redis Streams through idempotent consumer design and transaction boundaries in our application logic. The ability to handle 10x traffic growth is achievable with a properly scaled Redis cluster, and the real-time nature of Redis makes it well-suited for future WebSocket integration.

## Consequences

**Pros:**
*   **Reduced Operational Complexity**: We already run Redis in production, reducing the learning curve and operational burden compared to introducing a new distributed system like Kafka.
*   **Faster Time to Value**: Leveraging existing infrastructure and familiarity allows for quicker setup and migration, meeting the crucial 2-week deadline for delivering value.
*   **Cost-Effective**: Avoids the significant infrastructure and expertise costs associated with deploying and managing a Kafka cluster or expensive managed Kafka services.
*   **Real-time Capabilities**: Redis's low-latency nature is highly beneficial for future real-time WebSocket push notifications.
*   **Consumer Groups**: Redis Streams' consumer groups simplify workload distribution and processing state management across multiple notification workers.
*   **At-Least-Once Delivery**: Achievable out-of-the-box with Redis Streams' consumer group acknowledgements.
*   **Feasible Exactly-Once Semantics**: While not native in the same way as Kafka's transactional API, exactly-once delivery for critical billing events can be implemented through application-level idempotent processing and atomic operations with PostgreSQL.

**Cons:**
*   **Scaling Limitations**: While Redis can scale, scaling Redis Streams to truly massive, petabyte-scale event streams might eventually become more complex than Kafka, potentially requiring sharding or moving to a more specialized solution in the very distant future.
*   **Message Retention Management**: Redis Streams' retention policies are configurable (e.g., by size or time), but Kafka is inherently designed for longer-term, immutable log storage, which might require more active management or design considerations for historical data with Redis Streams.
*   **No Native Transactional Guarantees**: Redis Streams doesn't offer the same built-in transactional write guarantees across multiple partitions/topics that Kafka provides, requiring more careful application-side design for complex exactly-once scenarios beyond simple idempotent processing.
*   **Fewer Ecosystem Tools**: While the Redis ecosystem is rich, Kafka's ecosystem for stream processing, connectors, and monitoring is more mature and extensive for enterprise-grade data pipelines.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-leading capabilities in distributed streaming platforms, high throughput, robust ordering guarantees, and strong support for exactly-once semantics through its transactional API.

**Reasons for Rejection:**
*   **High Operational Complexity**: Kafka is notoriously complex to deploy, manage, and scale, especially for a team without dedicated infrastructure engineers. This would likely exceed our modest budget and expertise constraints, leading to significant delays.
*   **Steep Learning Curve**: The team has no prior Kafka experience. The time required for the team to learn Kafka concepts, best practices, and operational tooling would far exceed the 2-week setup/migration timeline.
*   **Budget Constraints**: Self-hosting Kafka is costly in terms of engineering time and resources, and managed services like Confluent Cloud are too expensive at full scale given our current budget.
*   **Overkill for Initial Needs**: While capable of handling 10x traffic growth, the immediate need can be met by a simpler system, and the overhead of Kafka would be disproportionate to the current problem scope and team capabilities.
*   **Slower Time to Value**: The high barrier to entry for Kafka would delay the decoupling of notifications and the resolution of current performance and reliability issues.
