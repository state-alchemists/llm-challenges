# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing high latency (up to 8s spikes) and request timeouts. We suffer from silent failures and cascading failures due to external webhook dependencies. Critically, billing-critical notifications lack delivery guarantees.

**Constraints & Requirements:**
- **Team**: 6 engineers, no dedicated DevOps/Infra engineer.
- **Current Stack**: Python/Flask, PostgreSQL, Redis (already in production).
- **Targets**: 10x growth (up to 5k req/s peak), async processing, exponential backoff retries, and WebSocket support within 2 quarters.
- **Guarantees**: At-least-once delivery for all; exactly-once semantics for billing-critical events.
- **Timeline**: Must deliver value within 2 weeks.
- **Budget**: Modest; cannot afford high-cost managed services (e.g., Confluent Cloud).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Operational Simplicity**: We already run Redis in production for sessions and rate limiting. Adding Streams requires zero new infrastructure components, whereas Kafka would introduce a significant operational burden (Zookeeper/KRaft, JVM tuning, partition management) for a team with no Kafka experience.
2. **Sufficient Throughput**: Redis Streams can easily handle the 10x growth target (5k req/s), as it operates in-memory with extremely low latency.
3. **Consumer Groups**: Redis Streams provides consumer groups, allowing us to scale workers horizontally and track message acknowledgement (ACK), enabling the required retry logic and dead-letter handling.
4. **Delivery Guarantees**: 
   - **At-least-once**: Achieved through the PEL (Pending Entries List) and explicit ACKs.
   - **Exactly-once**: For billing events, we will implement an idempotency pattern (Idempotent Consumer) using Redis keys (e.g., `processed_event:{event_id}`) to ensure that even if a message is delivered twice, it is processed only once.
5. **Time-to-Value**: Since the infrastructure is already present, implementation is limited to code changes. This fits well within the 2-week delivery window.

## Consequences
**Pros:**
- **Low Overhead**: No new servers to manage, monitor, or patch.
- **Fast Implementation**: Minimal learning curve for the team; rapid deployment of the async producer/consumer pattern.
- **Performance**: Sub-millisecond latency for message ingestion.
- **Integrated Ecosystem**: Future WebSocket push notifications can leverage Redis Pub/Sub or Streams seamlessly.

**Cons:**
- **Memory Bounds**: Redis is an in-memory store. We must implement strict `MAXLEN` capping on streams to prevent OOM (Out of Memory) errors during massive spikes.
- **Persistence Trade-off**: While Redis has AOF/RDB, it is not as durable as Kafka's disk-based commit log. However, for notifications, this risk is acceptable given the idempotency layer and PostgreSQL as the source of truth for billing events.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Complexity**: The "cost of entry" is too high. A 6-person team without a dedicated infra engineer would spend more time managing the cluster than building features.
- **Overkill for Scale**: While Kafka excels at millions of events per second and long-term retention, our 10x growth target (5k req/s) is well within the capabilities of Redis.
- **Deployment Lead Time**: Setting up a production-grade, highly available Kafka cluster would likely exceed the 2-week window for delivering initial value.
- **Cost**: Managed options that reduce operational burden (Confluent) exceed the current budget.
