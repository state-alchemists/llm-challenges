# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, blocking HTTP request cycles and causing significant latency spikes (up to 8s) and cascading failures. We lack retry mechanisms and delivery guarantees, which is critical for billing-related notifications.

**Constraints:**
- **Team:** 6 engineers (no dedicated DevOps/Infra).
- **Existing Stack:** Python/Flask, PostgreSQL, Redis.
- **Timeline:** Must deliver value within 2 weeks of setup.
- **Scaling:** Must handle 10x current traffic (~5,000 req/s peak).
- **Requirements:** At-least-once delivery for general events; exactly-once for billing events.
- **Future Goal:** WebSocket push notifications in 6 months.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives for an asynchronous event-driven architecture while staying within our operational and temporal constraints.

1. **Operational Simplicity:** We already run Redis in production for session storage. Adding Streams requires zero new infrastructure components and no new operational overhead for the team.
2. **Development Velocity:** The team has no Kafka experience. Implementing Redis Streams is a low-friction transition that fits the 2-week delivery window.
3. **Throughput & Scaling:** Redis Streams can easily handle 5,000+ req/s on a single instance, comfortably meeting our 10x growth target without requiring the complex partitioning logic associated with Kafka.
4. **Consumer Groups:** Redis Streams support consumer groups, allowing us to distribute notification processing across multiple workers, ensuring scalability and fault tolerance.
5. **Delivery Guarantees:** 
    - **At-least-once:** Achieved via explicit acknowledgement (`XACK`) and the Pending Entries List (PEL) for retries.
    - **Exactly-once:** While Redis doesn't provide native exactly-once across the entire pipeline, we will implement idempotency keys at the consumer level (stored in Redis/Postgres) to ensure billing notifications are processed exactly once.
6. **Future-Proofing:** Redis is an ideal companion for the upcoming WebSocket requirement (via Redis Pub/Sub or Streams), simplifying the real-time push architecture.

## Consequences

### Pros
- **Low Overhead:** No new binaries to manage, no JVM tuning, and no Zookeeper/KRaft complexity.
- **Rapid Deployment:** Immediate implementation using existing infrastructure.
- **Performance:** Sub-millisecond latency for producing and consuming events.
- **Unified Stack:** Keeps the infrastructure lean and maintains a smaller surface area for the 6-person team.

### Cons
- **Memory Bound:** Data is stored in RAM. We must implement a strict `MAXLEN` policy on streams to prevent OOM (Out of Memory) errors.
- **Persistence Trade-off:** While AOF (Append Only File) provides durability, it is not as robust as Kafka's disk-centric commit log for massive historical data retention.
- **Manual Idempotency:** Exactly-once delivery for billing requires application-level logic rather than a native broker feature.

## Alternatives Considered

### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity:** Kafka requires a significant investment in infrastructure management (brokers, controllers, schema registries). With no dedicated infra engineer, the "day 2" operations risk is too high.
- **Steep Learning Curve:** The team has zero Kafka experience. Learning the nuances of partitions, offsets, and consumer rebalancing would exceed the 2-week delivery constraint.
- **Cost:** Managed services like Confluent Cloud are outside the current modest budget, and self-hosting is too resource-intensive for the current team size.
- **Over-Engineering:** Kafka's massive throughput capabilities are not required for 5,000 req/s; it solves problems we do not currently have at the cost of agility.
