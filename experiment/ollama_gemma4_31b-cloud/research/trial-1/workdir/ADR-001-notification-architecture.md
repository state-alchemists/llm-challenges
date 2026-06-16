# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is implemented synchronously within the Flask request cycle, leading to request timeouts (up to 8s), silent failures during downstream outages, and cascading failures that exhaust connection pools.

**Key Constraints & Requirements:**
- **Team**: 6 engineers (no dedicated infra/SRE); no existing Kafka expertise.
- **Infrastructure**: Already running Redis in production for sessions/rate-limiting.
- **Timeline**: Deliver value within 2 weeks.
- **Budget**: Modest; managed Kafka (Confluent) is cost-prohibitive at scale.
- **Scaling**: Must support 10x current traffic (~5k req/s peak) and future WebSocket integration.
- **Guarantees**: At-least-once delivery for general events; exactly-once semantics required for billing-critical notifications (e.g., payment failures).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives for an asynchronous, durable message bus while aligning perfectly with our current operational constraints.

1. **Operational Complexity**: We already manage Redis. Adding Streams requires no new infrastructure, no new JVM/Zookeeper overhead (as required by Kafka), and no new monitoring stacks.
2. **Time-to-Value**: Given the lack of Kafka experience and the 2-week delivery window, Redis Streams allows the team to implement the producer/consumer pattern immediately using existing client libraries.
3. **Ordering & Consumer Groups**: Redis Streams supports consumer groups, allowing us to scale worker processes horizontally while maintaining message ordering per stream.
4. **Throughput**: Redis comfortably handles the target 10x growth (5k req/s), as it is an in-memory data structure with logarithmic time complexity for most stream operations.
5. **Exactly-Once Semantics**: While neither system provides "magic" exactly-once delivery across the wire, we will achieve it by combining Redis Streams' idempotency (via unique message IDs) with **idempotent consumers** in the application layer (tracking processed `event_id` in PostgreSQL). This is a standard pattern that avoids the extreme complexity of Kafka's transactional API.

## Consequences
### Pros
- **Zero New Infrastructure**: No additional cost or operational burden.
- **Low Latency**: Sub-millisecond producer latency, removing the blocking call from the HTTP request cycle.
- **Fast Migration**: Minimal learning curve for the existing team.
- **Flexible Consumption**: Supports both "fan-out" (for WebSockets/Emails) and "competing consumers" (for high-throughput webhooks).

### Cons
- **Memory Constraints**: Unlike Kafka, which stores data on disk, Redis is primary-memory. We will need to implement `MAXLEN` (capped streams) to prevent OOM, meaning very old undelivered messages may be dropped if not handled.
- **Persistence Trade-off**: While AOF/RDB provide persistence, Redis is generally less durable than Kafka's distributed commit log in the event of a catastrophic cluster failure.

## Alternatives Considered
### Apache Kafka
**Rejected**. While Kafka is the industry standard for high-throughput event streaming and offers superior long-term retention and durability, it was rejected for the following reasons:
- **Operational Overhead**: The "Kafka Tax" is too high for a 6-person team without an SRE. Managing brokers, Zookeeper/KRaft, and tuning JVMs would exceed the 2-week delivery window.
- **Budget**: Managed services (Confluent/MSK) are too expensive for our current stage.
- **Over-engineering**: Kafka's features (massive partition scaling, long-term log retention) far exceed our requirement of 5k req/s and basic notification retries.
