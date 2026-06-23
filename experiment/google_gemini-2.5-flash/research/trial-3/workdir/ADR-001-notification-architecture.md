# ADR 001 — Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-06-23
- **Deciders**: Engineering Team
- **Context tags**: notifications, asynchronous, message queue, Redis, Kafka

## Context

The existing notification module within our Python/Flask monolith synchronously sends emails and webhooks as part of the HTTP request cycle. This architecture has led to significant issues: request timeouts (average 800ms, spikes to 8s), silent failures when external services are down, cascading failures due to connection pool exhaustion from slow webhook endpoints, and a lack of delivery guarantees for critical billing notifications.

The system needs to be decoupled from the HTTP request cycle to process notifications asynchronously, support retry mechanisms with exponential backoff, and guarantee at-least-once delivery for all events, with exactly-once semantics for billing-critical messages. Future requirements include real-time WebSocket push notifications and handling 10x traffic growth (up to 5000 req/s) without a major re-architecture.

Key constraints influencing this decision include an engineering team of 6 (no dedicated infrastructure engineer), existing Redis usage for caching and session management, no prior Kafka experience within the team, a tight deadline of 2 weeks for initial value delivery, and a modest budget that precludes expensive managed Kafka solutions at full scale.

## Decision

We will use **Redis Streams** for the asynchronous notification subsystem.

This decision leverages our existing operational experience with Redis, significantly reduces the learning curve, and meets the immediate and projected scaling targets within the defined constraints. Redis Streams provides the necessary features for message queuing, consumer groups, and message retention, enabling us to implement reliable, decoupled notifications including exactly-once semantics for billing events.

## Rationale

Redis Streams is the optimal choice primarily due to the team's existing operational knowledge of Redis and the project's tight timeline and budget constraints. The "no Kafka experience on the team today" and "2 weeks of setup/migration" constraints strongly favor a solution that minimizes new infrastructure complexity and learning. Redis is already part of our production stack (`system_context.md`).

Redis Streams offers robust features for this use case:
- **Asynchronous Processing:** Streams allow producers to append messages without blocking the main request cycle.
- **Consumer Groups:** Built-in consumer group functionality simplifies distributing messages among multiple consumers, ensuring each message is processed by only one consumer within a group, and automatically tracking offsets. This is crucial for load balancing and fault tolerance.
- **At-least-once Delivery:** With consumer groups, messages are explicitly acknowledged (XACK), allowing for retries on failure and guaranteeing at-least-once delivery.
- **Exactly-once Semantics (for billing):** Can be achieved through a combination of client-side idempotent processing and careful use of consumer group acknowledgments, along with Redis's transaction capabilities where applicable.
- **Scalability:** Redis Streams can comfortably handle the current 500 req/s and the projected 10x traffic growth (5000 req/s) for notification volumes, especially when scaled horizontally with Redis Cluster.
- **Real-time Push Notifications:** Redis Pub/Sub, which can be integrated with Streams, or Streams themselves, can naturally support real-time WebSocket push notifications within two quarters.
- **Modest Budget:** Running Redis Streams on our existing Redis instances (or horizontally scaling Redis with a cluster if needed) is significantly more cost-effective than deploying and managing a Kafka cluster or paying for expensive managed Kafka services like Confluent Cloud.

## Alternatives Considered

- **Apache Kafka** — rejected due to high operational complexity and lack of team experience. While Kafka is a powerful, industry-standard streaming platform known for high throughput and strong delivery guarantees, its steep learning curve and the need for dedicated infrastructure management (brokers, ZooKeeper/Kraft, partitions, replication) would violate the "no dedicated infrastructure engineer" and "2 weeks of setup/migration" constraints. The modest budget also makes managed Kafka solutions at scale cost-prohibitive initially. Adopting Kafka would require a significant upfront investment in training and operational overhead, delaying value delivery.

## Consequences

- **Positive**:
    - Leverages existing Redis infrastructure and team knowledge, leading to faster implementation and lower operational overhead.
    - Decouples notification sending from the main application, resolving request timeouts and cascading failures.
    - Provides at-least-once delivery guarantees and enables exactly-once semantics for critical billing notifications.
    - Supports future real-time WebSocket push notifications with a consistent technology stack.
    - Cost-effective solution given the existing Redis deployment and modest budget.

- **Negative**:
    - Redis Streams, while performant, may not scale to the extreme throughput levels of Kafka (e.g., millions of messages per second across many petabytes of data) without careful tuning and potentially a more complex Redis Cluster setup. However, this is beyond our 10x scaling target.
    - Message retention in Redis Streams is primarily in-memory or on disk with AOF/RDB persistence. Long-term archival of all notification events might require moving data to a dedicated data warehouse if not managed carefully.

- **Follow-ups**:
    - Develop a clear strategy for managing Redis Streams' memory usage and message retention policies.
    - Implement robust retry logic with exponential backoff for notification consumers.
    - Design and implement client-side idempotency for billing notification consumers to ensure exactly-once processing.
    - Monitor Redis performance closely post-deployment to ensure the existing infrastructure can handle the increased load from Streams.
    - Investigate Redis Cluster for horizontal scalability if the 10x traffic growth exceeds single-instance capabilities.

## Backlinks

- [ADR index](index.md) (pending creation)
