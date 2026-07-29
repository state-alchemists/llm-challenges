# ADR 001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing high request latency (up to 8s), silent failures of third-party webhooks, and cascading failures that exhaust connection pools. We require a decoupled, asynchronous system that supports retries with exponential backoff and provides delivery guarantees—specifically "exactly-once" for billing-critical events.

**Key Constraints:**
- **Team:** 6 engineers, no dedicated infrastructure/DevOps specialist.
- **Existing Stack:** Redis is already in production; no Kafka expertise exists.
- **Timeline:** Value must be delivered within 2 weeks of setup.
- **Growth:** Must handle 10x growth (~5k req/s peak) and support future WebSocket integration.
- **Budget:** Limited; expensive managed Kafka services are not currently viable.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitives for a distributed message log (consumer groups, message persistence, and offset tracking) while fitting within our current operational capabilities. Since Redis is already deployed and managed by the team, the "time to value" is minimal, meeting the 2-week constraint. 

For the critical "exactly-once" requirement for billing, we will implement a **side-effect guard (idempotency key)** in the application layer using Redis keys. Neither Kafka nor Redis Streams provides true "exactly-once" delivery across the entire pipeline (producer $\rightarrow$ broker $\rightarrow$ consumer) without significant complexity; however, the combination of Redis Streams' `XACK` (acknowledgments) and an application-level idempotency check is the most pragmatic approach given the team size.

## Consequences
**Pros:**
- **Operational Simplicity:** Zero new infrastructure to deploy; utilizes existing Redis expertise.
- **Low Latency:** Redis provides sub-millisecond persistence, ensuring the HTTP request cycle is decoupled instantly.
- **Consumer Groups:** Supports scalable processing via consumer groups, allowing multiple workers to share the load.
- **Resource Efficiency:** Lower memory and CPU overhead compared to a JVM-based Kafka cluster for our current scale.
- **Future-Proof:** Readily supports the planned WebSocket push notifications (Redis Pub/Sub or Streams).

**Cons:**
- **Memory Bounds:** Redis is primarily an in-memory store. We must strictly manage stream lengths (`XADD` with `MAXLEN`) to avoid OOM errors if consumers fall behind.
- **Persistence Risk:** While AOF/RDB provides persistence, it is not as durable as Kafka's disk-first commit log. (Mitigated by using AOF with `everysec` for billing events).

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Complexity:** Kafka requires ZooKeeper (or KRaft) and significant tuning. Without a dedicated infra engineer, the risk of misconfiguration and "operational toil" is too high.
- **Learning Curve:** The team has zero Kafka experience. The time required to reach operational proficiency would exceed the 2-week delivery window.
- **Resource Overhead:** Kafka's footprint is overkill for a peak of 500-5,000 req/s.
- **Cost:** Managed options (Confluent) are budget-prohibitive, and self-hosting adds significant overhead.
