# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current synchronous notification system is causing request timeouts (spiking to 8s), silent failures of critical notifications, and cascading failures due to connection pool exhaustion. 

Key constraints and requirements include:
- **Delivery Guarantees**: At-least-once delivery for general notifications; exactly-once semantics for billing-critical events (e.g., payment failures).
- **Traffic**: Current peak of 500 req/s, with a requirement to scale 10x (5,000 req/s) without re-architecting.
- **Operational Capacity**: A small team of 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure engineer.
- **Existing Stack**: AWS, Python/Flask, PostgreSQL, and an existing Redis instance used for sessions/rate limiting.
- **Timeline**: Must be implemented within 2 weeks to deliver immediate value.
- **Future Needs**: Real-time WebSocket push notifications within 6 months.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the optimal balance between the required technical guarantees and the team's operational constraints.

1. **Operational Simplicity**: The team already manages Redis in production. Adding Streams requires no new infrastructure, no new monitoring stack, and no additional cost, satisfying the "modest budget" and "2-week setup" constraints.
2. **Throughput & Scaling**: Redis Streams easily handles the current 500 req/s and the projected 5,000 req/s. Since Redis operates primarily in-memory, latency for producer writes is minimal, solving the request timeout problem.
3. **Consumer Groups**: Redis Streams supports consumer groups, allowing us to distribute the notification load across multiple workers and track which messages have been processed.
4. **Delivery Guarantees**: 
   - **At-least-once**: Achieved via explicit acknowledgments (`XACK`). If a worker crashes before acknowledging, the message remains in the Pending Entries List (PEL) and can be claimed by another worker.
   - **Exactly-once (Billing)**: While Redis Streams provides at-least-once delivery, we will implement exactly-once semantics for billing events using **idempotency keys** stored in the existing PostgreSQL database. This is a standard pattern that avoids the extreme complexity of Kafka's transaction API.
5. **Future Integration**: Redis is the industry standard for powering WebSocket pub/sub and real-time notifications, making the transition to WebSocket push seamless.

## Consequences
### Pros
- **Zero Infrastructure Overhead**: No new clusters to deploy, secure, or patch.
- **Low Latency**: Immediate decoupling of the HTTP request cycle from notification delivery.
- **Fast Time-to-Market**: The team can implement the producer and consumer logic within the requested 2-week window.
- **Resource Efficiency**: Leverages existing memory and compute already allocated to the Redis instance.

### Cons
- **Memory Constraints**: Unlike Kafka, which persists to disk, Redis Streams reside in memory. We must implement a strict `MAXLEN` policy (capping stream length) to prevent OOM errors during massive spikes.
- **Persistence Trade-off**: While Redis offers AOF/RDB persistence, it is not as durable as Kafka's distributed commit log. However, given the 10x scale and nature of notifications, the risk is acceptable compared to the operational burden of Kafka.

## Alternatives Considered
### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity**: Kafka requires a dedicated Zookeeper or KRaft ensemble and significant tuning of JVM/OS parameters. With no dedicated infra engineer, the "hidden" cost of maintaining Kafka is too high.
- **Learning Curve**: The team has zero Kafka experience. Learning the nuances of partitions, offsets, and consumer rebalancing would exceed the 2-week delivery window.
- **Resource Cost**: Managed Kafka (e.g., Confluent) is outside the current modest budget, and self-hosting on AWS would require more instances than the current fleet.
- **Overkill**: Kafka is designed for multi-petabyte event streaming. For a system handling 5k req/s, the overhead of Kafka's distributed log is unnecessary compared to the lightweight nature of Redis Streams.
