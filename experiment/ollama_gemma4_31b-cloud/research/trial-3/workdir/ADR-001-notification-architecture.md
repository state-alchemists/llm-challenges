# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and embedded within the HTTP request cycle, leading to request timeouts (up to 8s), silent failures, and cascading failures due to slow external webhook endpoints. 

The system must evolve to decouple notifications from the request cycle, support exponential backoff retries, and ensure at-least-once delivery for general notifications and exactly-once delivery for billing-critical events.

**Constraints:**
- **Team:** 6 engineers (no dedicated infra engineer); no Kafka experience.
- **Existing Infra:** Already running Redis in production.
- **Timeline:** Must deliver value within 2 weeks of setup/migration.
- **Budget:** Modest; managed Confluent Cloud is currently unaffordable.
- **Scaling:** Must handle 10x growth (~5,000 req/s peak) and support future WebSocket integration.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitives for an asynchronous, distributed message queue (consumer groups, message acknowledgment, and persistence) while leveraging our existing operational knowledge and infrastructure. Given the team size and the strict 2-week time-to-value constraint, introducing Kafka would create an insurmountable operational burden.

Redis Streams satisfies the scaling target: at 5,000 req/s, Redis can easily handle the throughput on a single modest instance or a small cluster, and its low latency is ideal for the planned WebSocket push notifications.

## Consequences
**Pros:**
- **Operational Simplicity:** Zero new infrastructure to deploy or manage; we already run Redis.
- **Fast Time-to-Market:** The team can implement producers and consumers in Python using `redis-py` immediately without learning a new ecosystem.
- **Sufficient Performance:** Redis Streams easily handles the projected 10x growth in throughput.
- **Consumer Groups:** Allows us to distribute notification processing across multiple workers and track which messages were processed via PEL (Pending Entries List).

**Cons:**
- **Memory Constraints:** Unlike Kafka's disk-based storage, Redis primarily stores streams in RAM. We will need to implement a strict `MAXLEN` policy to prune old streams to avoid OOM (Out of Memory) events.
- **Durability Trade-off:** While Redis offers AOF (Append Only File) for persistence, it is generally less durable than Kafka's distributed commit log. However, for notification purposes, this is an acceptable risk.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Complexity:** Kafka requires Zookeeper (or KRaft) and significant tuning of JVM, partitions, and replication factors. With no dedicated infra engineer, the team would spend more time managing the cluster than building features.
- **Learning Curve:** The team has zero Kafka experience. The "2 weeks to deliver value" constraint would be violated by the learning curve and setup phase.
- **Overkill for Scale:** While Kafka is superior for massive data pipelines and long-term retention, our 10x target (~5,000 req/s) does not justify the complexity.
- **Cost:** Self-hosting Kafka on AWS would increase infrastructure overhead, and managed services (Confluent) are beyond the current budget.

**Exactly-Once Semantics Note:**
Neither Kafka nor Redis Streams provides "out-of-the-box" exactly-once delivery across the entire distributed pipeline (Producer $\rightarrow$ Broker $\rightarrow$ Consumer $\rightarrow$ External API). To achieve exactly-once for billing notifications, we will implement **idempotent consumers** using a unique `notification_id` stored in PostgreSQL, ensuring that a billing event is processed only once regardless of the transport layer's guarantees.
