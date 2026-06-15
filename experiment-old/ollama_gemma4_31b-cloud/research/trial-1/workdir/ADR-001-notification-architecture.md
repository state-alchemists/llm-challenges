# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing request timeouts (up to 8s) and cascading failures due to slow external webhooks. We lack delivery guarantees and retry mechanisms, specifically for billing-critical events.

**Requirements:**
- **Asynchronous Processing**: Decouple notifications from the HTTP cycle.
- **Reliability**: At-least-once delivery for general notifications; exactly-once where feasible for billing.
- **Scalability**: Support 10x traffic growth (peak ~5,000 req/s).
- **Future-proofing**: Support WebSocket push notifications within 2 quarters.
- **Operational Constraints**:
    - Team of 6 (no dedicated Infra engineer).
    - No existing Kafka experience.
    - Redis is already running in production.
    - Strict 2-week window for initial value delivery.
    - Limited budget (no managed Confluent Cloud).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitive for a durable, append-only log with consumer group support, allowing us to achieve the required decoupling and reliability without introducing significant operational overhead.

1. **Operational Simplicity**: Since Redis is already in production, we avoid the "Day 2" operational burden of managing a Zookeeper/Kafka cluster or the high cost of managed Kafka.
2. **Development Velocity**: The team can implement the producer/consumer pattern using existing Redis clients immediately, fitting within the 2-week delivery window.
3. **Performance**: With a peak target of 5,000 req/s, Redis Streams easily handles the throughput. Its in-memory nature ensures low latency for the producer (the Flask app).
4. **Consumer Groups**: Redis Streams supports consumer groups, enabling us to scale workers and ensure that each notification is processed by only one worker in a group (solving the "at-least-once" requirement).
5. **Exactly-Once Semantics**: While neither system provides "free" exactly-once delivery for external side effects (emails/webhooks), we will implement the **Idempotent Consumer** pattern using Redis keys to ensure billing notifications are not processed twice.

## Consequences
### Pros
- **Zero New Infrastructure**: Leverages existing Redis deployment, minimizing setup time and cost.
- **Low Latency**: Extremely fast append operations to streams.
- **Simpler Scaling**: Adding more consumer workers is trivial.
- **Feature Alignment**: Perfect synergy with the planned WebSocket push notifications (Redis Pub/Sub or Streams).

### Cons
- **Memory Constraints**: Persistent streams consume RAM. We must implement a strict retention policy using `XADD` with `MAXLEN` to prevent OOM.
- **Durability Trade-off**: Redis AOF (Append Only File) provides good durability, but is generally less robust than Kafka's disk-centric commit log. Given the 10x growth target, we may eventually need to move to a dedicated Redis cluster.

## Alternatives Considered
### Apache Kafka
Kafka was rejected due to **operational misalignment**.
- **Complexity**: Managing a Kafka cluster requires specialized knowledge that the current 6-person team lacks.
- **Onboarding Cost**: The 2-week delivery window would be consumed by infrastructure setup and learning curves rather than feature delivery.
- **Overkill**: While Kafka handles higher throughput and provides better long-term durability, our 10x target (~5k req/s) is well within Redis Streams' capabilities.
- **Cost**: Without a managed service (too expensive), the overhead of self-hosting Kafka would detract from core product development.
