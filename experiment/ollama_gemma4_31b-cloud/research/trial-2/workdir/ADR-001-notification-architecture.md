# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and coupled to the HTTP request cycle, leading to request timeouts, cascading failures due to slow downstream webhooks, and silent failures. The system lacks delivery guarantees for billing-critical notifications and cannot scale to the targeted 10x growth (up to 5,000 req/s peak).

**Constraints:**
- **Team:** 6 engineers, no dedicated infra specialist.
- **Knowledge:** Zero Kafka experience; existing Redis expertise.
- **Infrastructure:** Redis is already running in production.
- **Timeline:** Value must be delivered within 2 weeks.
- **Budget:** Modest; high-cost managed services (e.g., Confluent) are not feasible.
- **Requirements:** At-least-once delivery for general notifications; exactly-once semantics for billing; support for future WebSocket integration.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitives—consumer groups, message persistence, and acknowledgement (ACK) mechanisms—to solve the current reliability issues while fitting within the team's operational capacity.

1. **Operational Simplicity:** Since Redis is already in production, the "setup" time is near zero. Introducing Kafka would require deploying and managing a new cluster (Zookeeper/KRaft), which exceeds the 2-week delivery window and the team's current skill set.
2. **Throughput & Latency:** At 500 req/s (and even at the 10x target of 5,000 req/s), Redis Streams comfortably handles the load with sub-millisecond latency, far exceeding the current requirements.
3. **Delivery Guarantees:** Consumer groups allow for at-least-once delivery via PEL (Pending Entries List) and ACKs. Exactly-once semantics for billing will be achieved by implementing idempotency keys at the consumer level (checking against PostgreSQL), as neither Redis nor Kafka provides true end-to-end exactly-once without significant complexity.
4. **Future Growth:** Redis Streams supports the required fan-out pattern for future WebSocket push notifications.

## Consequences
**Pros:**
- **Immediate Deployment:** Leverages existing infrastructure; no new binaries or complex JVM tuning required.
- **Reduced Risk:** Low learning curve for the current team.
- **Performance:** Extremely high throughput and low latency for the current and projected load.
- **Resource Efficiency:** Minimal additional memory overhead compared to the heavy footprint of a Kafka cluster.

**Cons:**
- **Memory Bound:** Redis stores streams in RAM. While we can use `MAXLEN` to cap stream size, extreme spikes in unacknowledged messages could increase memory pressure.
- **Persistence Trade-off:** While AOF/RDB provide persistence, Redis is generally less durable than Kafka's disk-centric commit log in the event of a total cluster crash.

## Alternatives Considered
**Apache Kafka**
Rejected due to extreme operational complexity. Kafka requires a dedicated infrastructure effort to manage (cluster orchestration, partition tuning, JVM heap management) that a 6-person team without a DevOps specialist cannot sustain. The 2-week time-to-value constraint makes Kafka a non-starter. While Kafka offers superior long-term retention and stronger durability guarantees, these are overkill for the current scale and would introduce a significant "innovation tax" on the team's velocity.
