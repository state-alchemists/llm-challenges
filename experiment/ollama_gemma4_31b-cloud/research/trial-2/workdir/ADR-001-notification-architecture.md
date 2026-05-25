# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing request timeouts (up to 8s), silent failures, and cascading failures due to connection pool exhaustion. We need to decouple notification delivery from the HTTP request cycle to improve stability, ensure reliability for billing-critical events, and support future real-time WebSocket push notifications.

**Constraints:**
- **Team:** 6 engineers (3 senior, 3 mid) with no dedicated infra engineer and no Kafka experience.
- **Infrastructure:** Already running Redis (session/rate limiting) on AWS.
- **Time-to-Value:** Must be operational within 2 weeks.
- **Scale:** Peak 500 req/s, target 10x growth (5,000 req/s).
- **Requirements:** At-least-once delivery for most events; exactly-once semantics for billing-critical notifications.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Operational Simplicity:** Redis is already a production dependency. Using Redis Streams avoids introducing a new distributed system (Kafka), which would require new monitoring, backup, and maintenance protocols for a team with no Kafka expertise.
2. **Time-to-Value:** Deployment is near-instant. Implementation involves adding `XADD` to producers and `XREADGROUP` to consumers, meeting the <2-week requirement.
3. **Performance:** Redis Streams easily handle the current peak (500 req/s) and the 10x growth target (5,000 req/s), as Redis can process tens of thousands of operations per second with sub-millisecond latency.
4. **Ordering and Consumer Groups:** Redis Streams provide the required message ordering and consumer group semantics needed to distribute the workload across multiple worker processes.
5. **Delivery Guarantees:** 
    - **At-least-once:** Achieved via Consumer Group Acknowledgment (`XACK`).
    - **Exactly-once (Billing):** Since Redis Streams (like Kafka) provide at-least-once delivery, we will implement **idempotent processing** at the consumer level using a PostgreSQL unique constraint on `notification_id` and `event_type`. This is the industry standard for billing systems regardless of the broker.

## Consequences
**Pros:**
- **Zero Infrastructure Overhead:** No new software to install or manage.
- **Low Latency:** Minimal overhead for producing messages from the Flask monolith.
- **Developer Velocity:** The team can leverage existing Redis knowledge, reducing the risk of misconfiguration.
- **Future-Proof:** Provides the necessary foundation for WebSocket pushes by allowing a dedicated "push worker" to consume from the stream.

**Cons:**
- **Memory Bound:** Unlike Kafka's disk-based storage, Redis keeps streams in memory. We must implement a strict `MAXLEN` (capping stream length) to prevent OOM (Out of Memory) errors during massive spikes.
- **Persistence Trade-off:** While Redis AOF (Append Only File) provides durability, it is generally less robust for "infinite retention" than Kafka's distributed commit log. However, notifications are transient by nature, and we only need persistence until acknowledgment.

## Alternatives Considered
**Apache Kafka**
- **Reason for Rejection:** Kafka is an over-engineered solution for the current scale (~5k req/s). The operational complexity (Zookeeper/KRaft, JVM tuning, partition management) is too high for a 6-person team with no Kafka experience. The setup time would exceed the 2-week window, and the cost of managed services (Confluent) is currently prohibited by the budget. Kafka's "exactly-once" semantics (transactions) are powerful but would add significant complexity to the producer/consumer code that is better handled by database-level idempotency.
