---
Title: ADR-001-notification-architecture.md
---
# ADR 001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification module, part of a Python/Flask monolith, handles emails and webhooks synchronously within the HTTP request cycle. This has led to request timeouts, silent failures, cascading failures due to slow external dependencies, and a lack of delivery guarantees, especially for billing-critical notifications. The system currently serves 85,000 monthly active users and processes approximately 2 million tasks per month, with peak loads of ~500 req/s.

The goal is to decouple notifications, implement asynchronous processing, support retry mechanisms with exponential backoff, guarantee at-least-once delivery (and exactly-once for billing events), and enable future real-time WebSocket push notifications, all while supporting 10x traffic growth.

Key constraints include a small engineering team of 6 with no dedicated infrastructure engineer, existing Redis usage, no prior Kafka experience, a tight setup/migration timeline of two weeks, and a modest budget precluding expensive managed Kafka solutions at scale. Exactly-once semantics for billing notifications are a strict requirement.

## Decision
We will adopt **Redis Streams** for the notification subsystem.

This decision is primarily driven by the team's existing familiarity with Redis, the modest budget, the tight timeline for initial value delivery, and Redis Streams' ability to meet the critical "exactly-once" delivery requirement for billing notifications. While Kafka offers superior scalability and a richer ecosystem for complex event processing, the operational overhead and learning curve for a small team with no prior experience would be prohibitive given the constraints. Redis Streams provides a robust, lightweight, and performant solution that leverages existing infrastructure and team knowledge.

## Consequences

### Pros of Redis Streams:
*   **Operational Simplicity**: Leverages existing Redis infrastructure and team familiarity, significantly reducing the learning curve and operational burden. No new infrastructure to manage.
*   **Rapid Development**: Minimal setup and migration time (within the 2-week constraint) due to Redis already being in production. This allows for quick iteration and delivery of value.
*   **Exactly-Once Semantics (via Consumer Groups)**: Redis Streams inherently support consumer groups, allowing for distributed consumption and message acknowledgment, which is crucial for achieving at-least-once delivery. With careful client-side implementation (e.g., idempotent processing), exactly-once semantics for billing notifications can be achieved.
*   **Throughput**: Redis is known for high performance and low latency, which is suitable for the current and projected 10x traffic growth of 5000 req/s.
*   **Real-time Capabilities**: Well-suited for future WebSocket push notifications, as Redis Pub/Sub (which can be integrated with Streams) is a natural fit for real-time messaging.
*   **Message Retention**: Configurable message retention policies allow for replay of messages in case of consumer failures, aiding in retry mechanisms.

### Cons of Redis Streams:
*   **Scalability Limitations (compared to Kafka)**: While Redis is fast, a single Redis instance or cluster might eventually hit limitations for extremely high throughput or very large data volumes, especially if message retention is long. Kafka is designed for petabytes of data and millions of messages per second.
*   **Ecosystem Maturity**: The ecosystem around Redis Streams for complex stream processing, monitoring, and integration with other enterprise tools is less mature and extensive compared to Kafka.
*   **No Schema Enforcement**: Redis Streams do not inherently support schema enforcement, which can lead to issues if message formats are not strictly managed by the application layer.
*   **Durability and Replication Complexity**: Achieving strong durability and fault tolerance with Redis Streams requires careful configuration and management of Redis persistence (RDB/AOF) and replication, which can become complex at scale without a managed service.
*   **Limited Event Processing Features**: Redis Streams offer basic stream processing (e.g., range queries, consumer groups) but lack the advanced event processing capabilities (e.g., joins, windowing, aggregations) found in Kafka Streams or Flink.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-standard event streaming capabilities, high throughput, and robust ecosystem.

### Why Kafka was rejected:
*   **Operational Complexity & Learning Curve**: The primary reason for rejection. The engineering team has no prior Kafka experience and no dedicated infrastructure engineer. Setting up, operating, and maintaining a Kafka cluster (especially self-managed, given the budget constraints) would introduce significant operational overhead and a steep learning curve, directly violating the "2 weeks of setup/migration" constraint.
*   **Budget**: While managed Kafka services (like Confluent Cloud) simplify operations, they can be costly at full scale, exceeding the "modest budget" constraint. Self-hosting Kafka would require substantial investment in engineering time and expertise, which the team currently lacks.
*   **Timeline**: The time required to learn Kafka, set up a cluster, integrate it, and migrate existing notification logic would far exceed the two-week constraint for delivering initial value.
*   **Overkill for Initial Needs**: While Kafka excels at petabyte-scale data and millions of events per second, the initial 10x scaling target (5000 req/s) can be comfortably handled by Redis Streams. The complexity and features of Kafka might be overkill for the immediate problems, introducing unnecessary overhead.
*   **Exactly-Once Semantics**: While Kafka supports exactly-once semantics, implementing them correctly requires a deep understanding of Kafka's transaction API, which adds to the learning curve and implementation complexity for a team new to Kafka. Redis Streams, with idempotent processing, can achieve this with less effort for the specific use case.

Given the current team size, budget, existing infrastructure, and immediate scaling targets, Redis Streams presents a more pragmatic and efficient solution to address the notification subsystem's challenges.
