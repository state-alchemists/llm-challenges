# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system operates synchronously within the HTTP request cycle of our Flask monolith. This has led to request timeouts (up to 8s during peaks), silent failures of emails/webhooks, and cascading failures causing connection pool exhaustion. 

We must decouple these processes to ensure reliability and responsiveness. Key requirements include:
- **Reliability**: At-least-once delivery for general notifications and exactly-once semantics for billing-critical events.
- **Scalability**: Support 10x growth (from 500 req/s peak to ~5,000 req/s).
- **Future Growth**: Capability to integrate real-time WebSocket push notifications within 6 months.
- **Operational Constraints**: 
    - Team of 6 (no dedicated infra engineer).
    - Zero existing Kafka experience.
    - Existing production Redis instance used for sessions/rate limiting.
    - Tight timeline (maximum 2 weeks for initial value delivery).
    - Modest budget (cannot afford full-scale managed Confluent Cloud).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provide a lightweight, high-performance append-only log that satisfies our technical requirements while fitting perfectly within our operational constraints.

1. **Operational Simplicity**: We already run Redis in production. Implementing Streams requires no new infrastructure, no new monitoring stacks, and no specialized knowledge.
2. **Throughput & Latency**: Redis Streams easily handle the target 5,000 req/s peak with sub-millisecond latency, meeting the 10x growth target without a re-architecture.
3. **Consumer Groups**: Redis Streams support consumer groups, allowing us to distribute notification processing across multiple workers and track which messages have been acknowledged.
4. **Delivery Guarantees**: 
    - **At-least-once**: Achieved via the `XACK` (acknowledgment) mechanism and the ability to claim pending entries (`XPENDING`/`XCLAIM`) that failed to process.
    - **Exactly-once**: For billing-critical events, we will implement **idempotent processing** at the consumer level using a unique event ID stored in PostgreSQL. Given the scale and constraints, this is more pragmatic than attempting to manage Kafka's transactional producers.
5. **Time-to-Value**: Integration can be achieved within days using existing Python libraries, meeting the 2-week constraint.

## Consequences
### Pros
- **Low Overhead**: No additional servers or complex JVM tuning required.
- **Unified Tooling**: Leverages existing Redis expertise and monitoring.
- **Performance**: extremely low latency for both producer and consumer.
- **Flexibility**: Supports both a "fan-out" pattern (for different notification types) and a "worker queue" pattern.

### Cons
- **Memory Bound**: Unlike Kafka, Redis stores data in RAM. We will need to implement a strict retention policy using `XADD` with `MAXLEN` to prevent OOM (Out of Memory) crashes.
- **Persistence Trade-off**: While Redis offers AOF/RDB, it is not as durable as Kafka's disk-based commit log. However, for notifications, the risk of minimal data loss during a catastrophic crash is acceptable compared to the operational risk of managing Kafka.

## Alternatives Considered
### Apache Kafka
Kafka was rejected primarily due to **operational complexity** and **team constraints**.
- **Operational Burden**: Kafka requires a ZooKeeper/KRaft ensemble and significant tuning of JVM, disk I/O, and network settings. Without a dedicated infra engineer, this introduces a high risk of instability.
- **Learning Curve**: The team has zero Kafka experience. The time required to reach operational proficiency would exceed the 2-week window for delivering value.
- **Cost**: A self-hosted cluster adds significant AWS compute costs, and managed options like Confluent Cloud are outside the current modest budget.
- **Overkill**: While Kafka excels at multi-terabyte retention and massive scale, Redis Streams are more than sufficient for our projected 10x growth (thousands of req/s).
