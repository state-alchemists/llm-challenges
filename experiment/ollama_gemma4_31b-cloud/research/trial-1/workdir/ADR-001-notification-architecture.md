# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, blocking HTTP requests and causing timeouts (up to 8s) and cascading failures. We lack delivery guarantees, making billing-critical notifications (e.g., trial expirations) unreliable.

**Constraints:**
- **Team:** 6 engineers; no dedicated infrastructure/DevOps specialist.
- **Infrastructure:** Existing Redis deployment for sessions/rate limiting.
- **Knowledge:** No team experience with Kafka.
- **Timeline:** Maximum 2 weeks for setup/migration.
- **Scale:** 500 req/s peak, 10x growth target.
- **Requirements:** At-least-once delivery for all; exactly-once for billing; support for future WebSocket integration.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Redis Streams provides a lightweight, append-only log that satisfies our throughput requirements (10x growth to 5k req/s is well within Redis's capability) and ordering guarantees without the massive operational overhead of Kafka. Since Redis is already running in production, the "time to value" is near-zero, fitting within the 2-week constraint. We can achieve at-least-once delivery via Consumer Groups and acknowledge (ACK) semantics. For billing-critical "exactly-once" requirements, we will implement idempotency keys at the consumer level (database-backed), as true exactly-once is computationally expensive and operationally complex in any distributed system.

## Consequences
**Pros:**
- **Low Operational Overhead:** No new infrastructure to manage, monitor, or secure.
- **Immediate Implementation:** Leverages existing Redis expertise and deployment.
- **Performance:** Extremely low latency for producer writes; supports the required throughput.
- **Flexibility:** Consumer Groups allow scaling the number of notification workers as traffic grows.
- **Path to WebSockets:** Redis Pub/Sub or Streams can easily feed into a WebSocket gateway.

**Cons:**
- **Memory Bound:** Redis stores data in RAM; high retention periods for large volumes of notifications could increase costs. (Mitigation: Use short retention/MAXLEN policies).
- **Durability Trade-off:** While AOF provides durability, it is not as robust as Kafka's disk-centric storage. (Mitigation: Notifications are transient by nature; idempotency handles redelivery).

## Alternatives Considered
**Apache Kafka**
Rejected due to operational complexity and team constraints. Kafka requires a dedicated cluster (or expensive managed service like Confluent), Zookeeper/Kraft management, and significant tuning for "exactly-once" semantics (idempotent producers, transactional writes). Given the team size (6 people) and the lack of Kafka experience, the learning curve and management burden would exceed the 2-week migration window and introduce significant risk to system stability.
