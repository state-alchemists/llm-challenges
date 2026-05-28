# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system operates synchronously within the Flask request cycle, leading to high latency (spikes up to 8s), request timeouts, and cascading failures when external webhook endpoints are slow. We have no retry mechanism or dead-letter queues, resulting in silent failures for critical billing notifications.

**Constraints & Requirements:**
- **Scale:** 500 req/s peak; must handle 10x growth (5k req/s).
- **Reliability:** At-least-once delivery for all; exactly-once for billing events.
- **Team:** 6 engineers (no dedicated Infra/DevOps).
- **Existing Stack:** AWS, Python/Flask, PostgreSQL, and an existing Redis instance.
- **Timeline:** Rapid delivery (under 2 weeks for initial value).
- **Budget:** Modest; no expensive managed Kafka services.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Infrastructure Leverage:** We already operate Redis in production. Adding Streams requires zero new infrastructure components, fitting the 2-week delivery window and the "no dedicated infra engineer" constraint.
2. **Performance:** Redis Streams comfortably handle the current 500 req/s and the 10x target (5k req/s) with sub-millisecond latency, far exceeding our requirements.
3. **Consumer Groups:** Redis Streams provide consumer groups, allowing us to scale the number of worker processes independently and track message acknowledgment (ACK), enabling reliable retries and dead-letter handling.
4. **Ordering & Retention:** It provides a durable, append-only log with strong ordering guarantees per stream, which is sufficient for notification sequencing.
5. **Simplified Complexity:** Unlike Kafka, Redis does not require Zookeeper or a complex JVM-based runtime, reducing the operational burden on a small team.

To achieve **exactly-once semantics** for billing notifications, we will implement a "Consumer Idempotency" pattern: workers will use a PostgreSQL transaction to record the processed `message_id` in an `idempotency_keys` table before triggering the external notification.

## Consequences
**Pros:**
- **Fast Time-to-Market:** Immediate deployment using existing Redis infrastructure.
- **Low Operational Overhead:** No new monitoring, backup, or scaling strategies needed for a new cluster.
- **Efficient Resource Usage:** Significantly lower memory and CPU footprint compared to a Kafka cluster.
- **Ready for Future Growth:** Supports the planned WebSocket push notifications by allowing real-time consumers to tail the streams.

**Cons:**
- **Memory Constraints:** Unlike Kafka's disk-based storage, Redis stores streams in RAM (though `MAXLEN` can be used to prune). We must monitor memory usage as the volume grows.
- **Lower Durability Ceiling:** While Redis AOF provides durability, it is generally less robust than Kafka's distributed commit log for multi-terabyte retention. (Irrelevant given our 10x scale target is still modest).

## Alternatives Considered
**Apache Kafka**
Rejected for the following reasons:
- **Operational Complexity:** Kafka requires significant expertise for tuning, partition management, and cluster maintenance. The team currently has zero Kafka experience.
- **Over-Engineering:** Our throughput requirements (peak 5k req/s) do not justify the overhead of a distributed log system designed for millions of events per second.
- **Cost & Lead Time:** Setting up a production-grade, highly available Kafka cluster (or paying for Confluent Cloud) would exceed the modest budget and the 2-week delivery constraint.
- **Deployment Friction:** Introducing a new heavy dependency into the stack increases the surface area for failures without providing a proportional benefit over Redis Streams for this specific use case.
