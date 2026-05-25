# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system operates synchronously within the HTTP request cycle of a Python/Flask monolith. This has led to request timeouts (spikes up to 8s), silent failures due to lack of retries, and cascading failures (connection pool exhaustion) caused by slow external webhook targets.

The system must evolve to support:
- Asynchronous decoupling of notifications from the request cycle.
- Reliable delivery (at-least-once for general, exactly-once for billing events).
- Support for retry logic with exponential backoff.
- Ability to scale to 10x current peak traffic (~5,000 req/s).
- Future integration of WebSocket push notifications.

**Constraints:**
- Team: 6 engineers; no dedicated DevOps/Infra specialist.
- Infrastructure: Existing Redis deployment; no Kafka experience.
- Timeline: < 2 weeks for initial value delivery.
- Budget: Modest; precludes high-cost managed Kafka services.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides a lightweight, persistent append-only log that satisfies our requirements while aligning with our operational constraints:

1. **Operational Simplicity**: We already run Redis in production. Introducing Redis Streams requires no new infrastructure components, no new JVM tuning, and no ZooKeeper/KRaft management, which is critical for a 6-person team without a dedicated infra engineer.
2. **Performance & Throughput**: At a projected peak of 5,000 req/s, Redis Streams easily handles the load with sub-millisecond latency, far exceeding the requirements for a notification system.
3. **Consumer Groups**: Redis Streams supports consumer groups, allowing us to distribute the notification load across multiple worker processes to ensure scalability and fault tolerance.
4. **Delivery Guarantees**: 
   - **At-least-once**: Achieved via the `XACK` (acknowledgment) mechanism. Messages are not removed from the Pending Entries List (PEL) until acknowledged.
   - **Exactly-once (Billing)**: While Redis Streams provides at-least-once delivery, we will achieve "effectively exactly-once" for billing events by implementing **idempotency keys** in the consumer layer (backed by the existing Redis cache), ensuring a billing notification is processed once regardless of retries.
5. **Time to Value**: Integration can be completed within the 2-week window using existing Python libraries (`redis-py`), avoiding the steep learning curve associated with Kafka's producer/consumer API and partition management.

## Consequences
### Pros
- **Zero New Infrastructure**: Leverages existing Redis deployment, reducing operational overhead and cost.
- **Low Latency**: Faster producer/consumer cycle compared to Kafka for the current scale.
- **Simplified Tooling**: The team can use existing Redis CLI tools for debugging and monitoring.
- **Fast Migration**: Rapid deployment due to familiarity with the data store.

### Cons
- **Memory Constraints**: Redis is primarily an in-memory store. We must carefully manage stream lengths using `XADD` with the `MAXLEN` option to prevent memory exhaustion.
- **Persistence Trade-offs**: While Redis offers AOF/RDB, it is generally less durable than Kafka's disk-centric commit log. However, for notifications, the risk of losing a few milliseconds of data in a catastrophic crash is acceptable compared to the operational risk of managing a Kafka cluster.

## Alternatives Considered
### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity**: Kafka is a significant "heavy lift" for a team of 6 without infra specialists. Managing brokers, partitions, and offsets introduces substantial cognitive load and operational risk.
- **Over-Engineering**: Kafka's massive throughput capabilities are unnecessary for a target of 5,000 req/s; the overhead of the JVM and the complexity of its ecosystem (Schema Registry, Connect) provide no immediate value for this specific use case.
- **Cost**: A self-hosted cluster requires dedicated resources; managed solutions (Confluent) exceed the current modest budget.
- **Learning Curve**: No prior team experience would push the "time to value" beyond the required 2-week window.
