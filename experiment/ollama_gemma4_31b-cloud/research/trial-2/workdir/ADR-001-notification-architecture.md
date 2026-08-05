# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, blocking HTTP requests and causing timeouts (up to 8s) and cascading failures. The system lacks delivery guarantees, retries, and dead-letter queues, which is critical for billing-related notifications.

**Key Constraints:**
- **Team:** 6 engineers, no dedicated DevOps/Infra engineer.
- **Infrastructure:** Existing Redis instance in production. No Kafka experience.
- **Performance:** Peak 500 req/s; target 10x growth (5,000 req/s).
- **Requirements:** At-least-once delivery for general notifications; exactly-once semantics for billing.
- **Timeline:** Must be implementable within 2 weeks.
- **Budget:** Modest; managed Kafka (Confluent) is cost-prohibitive.

## Decision
We will use **Redis Streams** as the message backbone for the notification subsystem.

### Justification
Given the constraints, Redis Streams provides the best balance of technical capability and operational simplicity.

1. **Operational Complexity:** The team already manages Redis. Introducing Kafka would require learning a new ecosystem (Zookeeper/KRaft), managing a new set of JVM-based processes, and handling significantly higher memory/disk overhead. With no dedicated infra engineer, the "cognitive load" of Kafka is a primary risk.
2. **Throughput & Scaling:** Redis Streams can comfortably handle the 10x growth target (5,000 req/s). Since notifications are I/O bound (emails, webhooks), the bottleneck will be the external providers, not the Redis throughput.
3. **Consumer Groups:** Redis Streams supports consumer groups (similar to Kafka), allowing us to scale the notification workers horizontally and track which messages have been acknowledged.
4. **Ordering & Persistence:** Redis Streams provides an append-only log with strict ordering per stream, satisfying the requirement for sequential processing of task updates.
5. **Exactly-Once Semantics:** While neither Kafka nor Redis provides "true" exactly-once delivery across the network (due to the Two Generals' Problem), we can achieve effective exactly-once processing for billing notifications by using Redis as a distributed lock/idempotency store (which we already have) combined with the stream's acknowledgement mechanism.
6. **Time-to-Value:** Integration with the existing Python/Flask stack via `redis-py` is trivial. Setup is a configuration change rather than a new infrastructure deployment, fitting the 2-week window.

## Consequences
### Pros
- **Low Overhead:** No new infrastructure to provision, monitor, or patch.
- **Rapid Deployment:** Immediate start on implementation using existing Redis instances.
- **Unified Stack:** Keeps the data layer simple; Redis serves as both cache and message broker.
- **Performance:** Extremely low latency for message ingestion.

### Cons
- **Memory Constraints:** Unlike Kafka, which persists to disk by default, Redis is primarily in-memory. We must carefully manage stream length (using `XADD` with `MAXLEN` or `MINID`) to avoid OOM (Out of Memory) events.
- **Persistence Trade-off:** While Redis AOF/RDB provides persistence, it is generally less durable than Kafka's distributed commit log in the event of a total cluster failure.
- **Limited Ecosystem:** Fewer "out-of-the-box" connectors (like Kafka Connect) compared to the Kafka ecosystem.

## Alternatives Considered
### Apache Kafka
Kafka was rejected primarily due to **operational misalignment**.
- **Complexity:** Kafka's operational burden (partition management, offset commits, JVM tuning) is too high for a 6-person team without a DevOps engineer.
- **Overkill:** Kafka is designed for multi-gigabyte/sec throughput and massive retention. Our 10x growth target is still well within the capabilities of a well-tuned Redis cluster.
- **Cost/Time:** Deploying a production-grade, highly available Kafka cluster would exceed the 2-week implementation window and the modest budget.
