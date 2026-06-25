# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to request timeouts (up to 8s), silent failures, and cascading failures due to connection pool exhaustion. We must decouple notifications from the HTTP request cycle to support retries with exponential backoff and ensure at-least-once delivery for billing-critical events.

**Key Constraints:**
- **Team:** 6 engineers (3 senior, 3 mid); no dedicated DevOps/Infrastructure engineer.
- **Existing Stack:** Python/Flask, PostgreSQL, AWS, and an existing production Redis instance.
- **Knowledge Gap:** Zero team experience with Apache Kafka.
- **Timeline:** Implementation must provide value within 2 weeks.
- **Scaling:** Must handle 10x current peak (500 req/s $\rightarrow$ 5,000 req/s).
- **Requirement:** Exactly-once semantics for billing notifications.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
Given the team size and the "no dedicated infra" constraint, operational simplicity is the primary driver. Redis Streams provides the necessary primitive for a distributed append-only log without the massive overhead of a Kafka cluster.

1. **Operational Complexity:** We already run Redis in production. Adding Streams is a configuration/logic change rather than a new infrastructure deployment. Kafka requires Zookeeper (or KRaft), JVM tuning, and complex partition management.
2. **Throughput & Scaling:** Redis Streams can easily handle 5,000 req/s (10x growth), as the current peak is only 500 req/s. The memory-first architecture is sufficient for the expected volume of notification events.
3. **Consumer Groups:** Redis Streams supports Consumer Groups (`XGROUP`), allowing us to scale workers horizontally and track message delivery (ACKs), satisfying the requirement for decoupled async processing.
4. **Time-to-Value:** Integration with the existing Redis instance allows us to move from synchronous to asynchronous processing in days, fitting comfortably within the 2-week window.
5. **Exactly-Once Semantics:** While neither system guarantees exactly-once delivery out-of-the-box across the entire pipeline, we will achieve it for billing events by combining Redis Streams with **idempotent consumers** in PostgreSQL (using a `processed_events` table with unique transaction IDs).

## Consequences
### Pros
- **Zero New Infrastructure:** No new servers, licenses, or monitoring stacks to manage.
- **Low Latency:** Extremely high throughput and low latency for message ingestion.
- **Team Velocity:** The team can use existing Python Redis clients (`redis-py`) without a steep learning curve.
- **Future Proofing:** Consumer Groups provide a clear path toward adding WebSocket push notifications by simply adding another consumer group to the same stream.

### Cons
- **Memory Constraints:** Redis stores streams in RAM. We must implement a strict `MAXLEN` policy (eviction) to prevent OOM, shifting the burden of long-term persistence to the database or a cold-storage archive if needed.
- **Lower Durability Guarantee:** Unlike Kafka's disk-first approach, Redis's AOF/RDB snapshots have a small window of potential data loss in the event of a catastrophic crash, though this is acceptable for notifications given the "at-least-once" target.

## Alternatives Considered
### Apache Kafka
**Rejected.** While Kafka is the industry standard for high-throughput event streaming and provides superior durability and offset management, it is overkill for this scale.
- **Operational Overhead:** Managing a Kafka cluster without a dedicated infra engineer would distract the 6-person team from product delivery.
- **Learning Curve:** The team has zero Kafka experience; the time required to correctly configure partitions, replication factors, and consumer offsets would exceed the 2-week delivery window.
- **Cost:** Managed services like Confluent Cloud are outside the current modest budget.
