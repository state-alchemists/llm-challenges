# ADR 001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to request timeouts (up to 8s), silent failures due to lack of retries, and cascading failures caused by slow downstream webhooks. We have a critical requirement to move to asynchronous processing to decouple notifications from the HTTP request cycle.

Key constraints and requirements include:
- **Delivery Guarantees**: At-least-once delivery for most events; exactly-once semantics for billing-critical notifications.
- **Scalability**: Support 10x current peak traffic (~5,000 req/s).
- **Team**: 6 engineers (3 senior, 3 mid) with no Kafka experience and no dedicated infra engineer.
- **Infrastructure**: Currently running Redis in production on AWS.
- **Timeline**: Value must be delivered within 2 weeks of setup/migration.
- **Future Scope**: Integration of real-time WebSocket push notifications within 2 quarters.

## Decision
We will use **Redis Streams** as the messaging backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives for an asynchronous event system (consumer groups, message persistence, and acknowledgement) while aligning with our operational constraints:

1. **Operational Simplicity**: We already manage Redis in production. Introducing Kafka would require deploying and managing a new, complex distributed system (ZooKeeper/KRaft, JVM tuning, partition management) without a dedicated infra engineer.
2. **Time-to-Value**: Setup is trivial given existing infrastructure. We can implement the producer/consumer pattern in days, fitting comfortably within the 2-week window.
3. **Performance**: Redis Streams easily handles the targeted 5,000 req/s with sub-millisecond latency, satisfying the 10x growth target.
4. **Delivery Guarantees**: 
   - **At-least-once**: Achieved via Consumer Groups and the `XACK` mechanism.
   - **Exactly-once (Billing)**: Since Redis does not provide native global exactly-once semantics across producers and consumers, we will implement **Idempotent Consumers** using a deduplication table in PostgreSQL. The combination of a unique Event ID in the stream and a transactional check in the DB ensures billing notifications are processed exactly once.
5. **Future Proofing**: Redis's Pub/Sub and Stream capabilities integrate naturally with the planned WebSocket push notifications.

## Consequences

### Pros
- **Zero Infrastructure Overhead**: No new software to install, monitor, or patch.
- **Low Learning Curve**: The team is already familiar with Redis; the Streams API is straightforward.
- **Resource Efficiency**: Leverages existing memory/CPU allocations for the Redis cluster.
- **Fast Iteration**: Rapid deployment and testing of the retry logic and DLQ (Dead Letter Queue) patterns.

### Cons
- **Memory-Bound Retention**: Unlike Kafka's disk-based storage, Redis primarily stores data in RAM. We must strictly manage stream lengths (using `XADD` with `MAXLEN`) to avoid OOM (Out of Memory) errors during massive traffic spikes.
- **Limited Long-term Replay**: If we need to replay events from months ago, we cannot rely on Redis; we will need to archive events to PostgreSQL or S3.
- **Manual Exactly-Once**: Requires application-level idempotency logic for billing events.

## Alternatives Considered

### Apache Kafka
Kafka was considered due to its superior throughput, disk-based retention, and robust ecosystem. However, it was rejected for the following reasons:
- **Operational Complexity**: The "Kafka tax" (management of brokers, partitions, and offsets) is too high for a 6-person team without a dedicated DevOps/SRE role.
- **Implementation Lag**: The learning curve for a team with zero Kafka experience would exceed the 2-week window for delivering value.
- **Cost**: Without a managed service like Confluent Cloud (which is budget-prohibited), the engineering cost of self-hosting and stabilizing a production Kafka cluster is unjustifiable for the current scale.
