# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to HTTP request timeouts (up to 8s), silent failures during provider outages, and cascading failures that exhaust connection pools. We need to decouple notification delivery from the request cycle to improve reliability and latency.

**Key Constraints & Requirements:**
- **Team:** 6 engineers (no dedicated infra specialist); no prior Kafka experience.
- **Infrastructure:** Existing Redis deployment in production.
- **Timeline:** Value must be delivered within 2 weeks.
- **Budget:** Limited; cannot afford high-cost managed Kafka services.
- **Technical Needs:** 
    - At-least-once delivery for all notifications.
    - Exactly-once semantics for billing-critical events (e.g., "payment failed").
    - Support for exponential backoff retries.
    - Scalability to 10x current peak (5,000 req/s).
    - Foundation for real-time WebSocket push notifications within 6 months.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives for a distributed message queue (consumer groups, message persistence, and acknowledgments) while fitting perfectly within our current operational constraints.

1. **Operational Complexity:** Since we already run Redis for session storage and rate limiting, the overhead of deploying and managing Redis Streams is near zero. In contrast, Kafka requires a separate cluster, ZooKeeper (or KRaft), and specialized tuning—skills the current team does not possess.
2. **Implementation Speed:** Using an existing infrastructure component allows the team to move from design to production within the 2-week window. Kafka's learning curve and setup would likely exceed this limit.
3. **Performance:** At 5,000 req/s (10x growth), Redis Streams is more than capable. While Kafka scales higher, our projected load does not justify the "Kafka tax" on developer productivity and infra budget.
4. **Exactly-Once Semantics:** While neither system provides "magic" exactly-once delivery across the entire pipeline (due to the Two Generals' Problem), Redis Streams allows us to implement idempotency via a combination of `XACK` and a unique `event_id` stored in our existing PostgreSQL database. This meets the requirement for billing-critical notifications.
5. **Future-Proofing:** Redis is natively suited for the upcoming WebSocket requirement (via Pub/Sub or Stream consumers), allowing for a unified real-time data layer.

## Consequences
### Pros
- **Zero New Infrastructure:** No new binaries to manage or servers to provision.
- **Low Latency:** Extremely high throughput and low latency for producers.
- **Rapid Time-to-Market:** Fast implementation due to existing Redis client libraries in our Python/Flask stack.
- **Simplified Tooling:** One less system to monitor and backup.

### Cons
- **Memory Bounds:** Redis is primarily an in-memory store. We must carefully configure stream capping (`XADD MAXLEN`) to prevent OOM (Out of Memory) errors if consumers lag significantly.
- **Persistence Trade-off:** Redis persistence (RDB/AOF) is generally less durable than Kafka's disk-centric commit log. However, for notifications, this risk is acceptable given our current scale.
- **Consumer Scaling:** While Redis Streams supports consumer groups, it is less flexible than Kafka's partition-based scaling for massive throughput (millions of events/sec).

## Alternatives Considered
### Apache Kafka
Kafka was rejected primarily due to **operational misalignment**.
- **Complexity:** The "cost of ownership" for Kafka (clustering, partition management, JVM tuning) is too high for a 6-person team without a dedicated DevOps engineer.
- **Budget:** Managed services like Confluent Cloud are cost-prohibitive for our current budget.
- **Over-Engineering:** Kafka is designed for massive data pipelines and stream processing. Our need is a reliable asynchronous task queue; using Kafka here would be "using a sledgehammer to crack a nut."
- **Setup Time:** The installation, configuration, and team training period would violate the 2-week delivery constraint.
