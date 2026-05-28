# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing request timeouts (up to 8s) and cascading failures due to slow third-party webhooks. We lack delivery guarantees, leading to silent failures for critical billing notifications. 

**Key Constraints:**
- **Traffic:** ~500 req/s peak, targeting 10x growth (5,000 req/s).
- **Team:** 6 engineers; no dedicated DevOps/Infra roles.
- **Existing Stack:** Python/Flask, PostgreSQL, and a production Redis instance.
- **Timeline:** Must deliver value within 2 weeks.
- **Requirements:** Async processing, exponential backoff retries, at-least-once delivery for general events, and exactly-once semantics for billing events.
- **Future Need:** Real-time WebSocket push notifications.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Given the team size and constraints, Redis Streams provides the most pragmatic balance between technical requirements and operational overhead. We already run Redis in production, eliminating the "day 0" infrastructure setup cost. Redis Streams supports the required consumer group model for parallel processing, message persistence for retries, and sufficient throughput to handle the 10x growth target (Redis can easily handle tens of thousands of writes/sec). For billing-critical "exactly-once" semantics, we will implement an idempotency layer in the Python consumer using the existing PostgreSQL database as the source of truth, which is a more reliable pattern than relying on the transport layer's native semantics.

## Consequences
### Pros
- **Zero New Infrastructure:** Leverages existing Redis deployment, meeting the 2-week delivery window.
- **Low Operational Complexity:** Team doesn't need to learn Kafka's cluster management, Zookeeper/KRaft, or complex partition tuning.
- **Performance:** Sub-millisecond latency for producers, decoupling the HTTP request cycle immediately.
- **Consumer Groups:** Allows us to scale the number of worker processes as traffic grows toward 5,000 req/s.
- **Prerequisite for WebSockets:** Redis Pub/Sub or Streams integrates natively with common WebSocket patterns for future push notifications.

### Cons
- **Memory Constraints:** Unlike Kafka (which stores to disk), Redis is primarily in-memory. We must implement strict `MAXLEN` policies to prevent memory exhaustion during massive spikes or consumer downtime.
- **Durability Trade-off:** While Redis offers AOF (Append Only File) persistence, it is generally less durable than Kafka's distributed commit log. However, given our scale and the ability to replay from PostgreSQL for critical events, this is an acceptable risk.

## Alternatives Considered

### Apache Kafka
Kafka was rejected primarily due to **operational misalignment**. 
- **Overkill for Scale:** While Kafka handles higher throughput than Redis, our 10x target (5,000 req/s) is well within Redis's capabilities.
- **High Operational Burden:** With no dedicated infra engineer, managing a Kafka cluster (even a small one) introduces significant risk. The learning curve for the 6-person team would exceed the 2-week delivery constraint.
- **Cost:** Managed services like Confluent Cloud are currently outside the modest budget.
- **Complexity:** Kafka's "exactly-once" semantics require strict configuration (idempotent producers, transaction coordinators) that adds complexity without providing more benefit than a simple DB-backed idempotency key in the consumer.
