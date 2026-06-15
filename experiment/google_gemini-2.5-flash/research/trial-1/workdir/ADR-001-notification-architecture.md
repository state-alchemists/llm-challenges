# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification module within our Python/Flask monolith is synchronous, leading to severe performance bottlenecks (request timeouts, latency spikes up to 8s), silent failures without retry, and cascading failures due to external service dependencies (e.g., slow webhooks exhausting connection pools). Critical billing notifications lack delivery guarantees, posing a significant business risk.

Our objective is to decouple notification processing from the HTTP request cycle, introduce async processing, implement retry mechanisms with exponential backoff, and guarantee at-least-once delivery for all notifications, with exactly-once semantics for billing events. We also need to support real-time WebSocket push notifications within two quarters and scale to 10x current traffic (5000 req/s peak).

Key constraints include:
- A small engineering team (6 people, no dedicated infrastructure engineer).
- Existing Redis deployment used for session management and rate limiting.
- No prior team experience with Kafka.
- A tight timeline of 2 weeks for initial setup and value delivery.
- A modest budget, precluding full-scale managed Confluent Cloud.
- Strict requirement for exactly-once semantics for billing notifications.

## Decision
We choose **Redis Streams** for the new notification subsystem.

This decision prioritizes leveraging existing infrastructure, minimizing operational overhead for our small team, and achieving rapid initial value delivery, all while meeting the core functional requirements for notification processing and future scaling needs.

## Consequences

### Pros
- **Leverages existing infrastructure**: Redis is already in production, reducing the learning curve and infrastructure footprint. The team is familiar with Redis operations and monitoring.
- **Lower operational complexity**: Redis Streams are simpler to operate than Kafka, especially for a team without dedicated infrastructure engineers. It avoids introducing a new, complex distributed system to manage.
- **Faster time-to-value**: Given the team's existing Redis knowledge and the simpler operational model, initial setup and migration work can likely be completed well within the 2-week constraint.
- **Good fit for current scale and growth**: Redis Streams offer sufficient throughput for our current 500 req/s and anticipated 10x growth (5000 req/s). Its consumer group model provides robust message processing, ordering guarantees within a stream, and at-least-once delivery.
- **Exactly-once semantics**: With careful application-level idempotent processing (e.g., using a unique message ID and checking a processed set in Redis or PostgreSQL), Redis Streams can support exactly-once semantics for billing-critical events.
- **Built-in retry and persistence**: Messages are persistent and can be acknowledged, allowing for retry mechanisms and dead-letter queue patterns.
- **Real-time capabilities**: Redis's pub/sub and Streams features are well-suited for building real-time WebSocket push notifications in the future.

### Cons
- **Limited ecosystem compared to Kafka**: While Redis Streams are powerful, the broader ecosystem of tools, connectors, and integrations (e.g., for CDC, advanced analytics) is not as extensive as Kafka's.
- **Scalability limits (eventual)**: For extreme, petabyte-scale data streaming or very high fan-out with billions of messages per second across thousands of topics, Kafka generally offers more robust scaling capabilities. However, Redis Streams are highly performant and scale well beyond our projected 10x growth, potentially to hundreds of thousands of messages per second on appropriate hardware.
- **Data retention**: While Redis Streams support configurable data retention, very long-term, immutable log storage (years of events) is not its primary strength, unlike Kafka. For our use case, this is not a strict requirement.
- **Single point of failure (if not clustered)**: A single Redis instance could be a SPOF. However, we already run Redis and can leverage existing or planned high-availability strategies (Redis Sentinel or Cluster) for robustness.

## Alternatives Considered

### Apache Kafka
Kafka was considered as a strong contender due to its industry-leading throughput, robust fault tolerance, and comprehensive ecosystem for stream processing. However, it was rejected primarily because:

- **High operational complexity**: Introducing Kafka would mean onboarding a completely new distributed system, requiring significant learning and operational overhead for a team with no prior Kafka experience and no dedicated infrastructure engineer. This directly conflicts with our constraint of a small team and modest budget, especially precluding managed Confluent Cloud.
- **Longer time-to-value**: The learning curve and setup time for Kafka (even self-managed) would likely exceed the 2-week constraint for delivering initial value, delaying the critical decoupling of notifications.
- **Budget constraints**: While open-source Kafka is free, the operational burden often drives teams towards managed services, which are currently outside our budget for full scale. Self-hosting requires significant expertise and resources to configure and maintain for production reliability.
- **Overkill for current needs**: While Kafka offers unparalleled scalability, it is arguably an over-engineered solution for our current 500 req/s and projected 5000 req/s. Redis Streams can comfortably handle these volumes with less complexity.

While Kafka provides strong guarantees for at-least-once and exactly-once processing (with Kafka Streams API), the overhead of adopting it outweighs its benefits for our specific team and project constraints at this stage. Redis Streams can meet the required delivery semantics with careful application design, without the steep operational cost.
