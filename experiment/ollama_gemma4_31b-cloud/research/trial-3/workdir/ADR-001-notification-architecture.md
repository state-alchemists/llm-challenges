# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing HTTP request timeouts (up to 8s), silent failures of emails/webhooks, and cascading system failures due to connection pool exhaustion. We need to decouple notifications from the request cycle to improve reliability and support 10x traffic growth (up to 5,000 req/s).

**Key Constraints:**
- **Team:** 6 engineers, no dedicated DevOps/Infra; no Kafka experience.
- **Timeline:** Value must be delivered within 2 weeks of setup.
- **Infrastructure:** Already running Redis in production.
- **Budget:** Modest; managed Kafka (Confluent) is currently too expensive.
- **Requirements:** 
    - At-least-once delivery for standard notifications.
    - Exactly-once semantics for billing-critical events.
    - Support for future WebSocket push notifications.
    - Retry with exponential backoff.

## Decision
We will use **Redis Streams** as the foundation for the notification subsystem.

### Justification
Redis Streams provides a lightweight, persistent append-only log that satisfies our technical requirements while aligning perfectly with our operational constraints.

1. **Operational Simplicity:** We already operate Redis. Adding Streams requires zero new infrastructure components, avoiding the "operational tax" of deploying and managing a Kafka cluster or paying for expensive managed services.
2. **Team Velocity:** The team has zero Kafka experience. Learning Kafka's complex ecosystem (Zookeeper/KRaft, partitions, consumer group offsets) would exceed the 2-week delivery window. Redis Streams uses a familiar API and mental model.
3. **Performance:** With a peak of 500 req/s and a 10x target (5k req/s), Redis Streams easily handles the throughput. Its low-latency characteristics are superior for the real-time WebSocket requirements planned for next quarter.
4. **Delivery Guarantees:** 
    - **At-least-once:** Achieved via Consumer Groups and explicit acknowledgments (`XACK`).
    - **Exactly-once:** While Redis Streams provides at-least-once delivery, we will implement exactly-once semantics for billing events by using a **deduplication pattern** (Idempotency Key) in the consumer, leveraging the existing Redis instance to track processed message IDs.
5. **Consumer Groups:** Redis Streams supports consumer groups, allowing us to scale the notification workers horizontally as traffic grows.

## Consequences
### Pros
- **Zero Infra Overhead:** No new binaries to install or clusters to manage.
- **Rapid Deployment:** Implementation can start immediately using existing libraries.
- **Unified Stack:** Keeps the infrastructure lean, reducing the surface area for failures.
- **Low Latency:** Ideal for the upcoming real-time WebSocket push feature.

### Cons
- **Memory Constraints:** Redis stores data in RAM. We must implement strict stream capping (`XADD ... MAXLEN ~`) to prevent OOM crashes as volume grows.
- **Persistence Trade-off:** While Redis has AOF/RDB, it is not as durable as Kafka's disk-based commit log. For billing events, we will ensure AOF is configured with `everysec` to minimize data loss risk.
- **Ecosystem:** Smaller ecosystem of third-party connectors compared to Kafka.

## Alternatives Considered
### Apache Kafka
**Rejected.** While Kafka is the gold standard for high-throughput event streaming and offers stronger durability and native exactly-once semantics (via transactional producers), it is overkill for our current scale (5k req/s). 

**Reasons for rejection:**
- **Operational Complexity:** Managing a Kafka cluster without a dedicated infra engineer is a significant risk to stability.
- **Learning Curve:** The time required for the team to become proficient in Kafka would jeopardize the 2-week delivery mandate.
- **Cost:** Managed Kafka services exceed the current modest budget.
- **Over-engineering:** The complexity of Kafka's partitioning and offset management is unnecessary for a notification system of this scale.
