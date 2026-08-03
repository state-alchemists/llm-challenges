# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and coupled to the HTTP request cycle, leading to request timeouts (spikes to 8s), silent failures of external providers, and cascading failures that cause connection pool exhaustion. 

The system must be decoupled to support asynchronous processing and retries with exponential backoff. Critical requirements include:
- **Delivery Guarantees**: At-least-once delivery for general notifications and exactly-once semantics for billing-critical events (e.g., trial expiration).
- **Scalability**: Support 10x growth (peak ~5,000 req/s) without re-architecting.
- **Future Growth**: Support real-time WebSocket pushes within two quarters.
- **Constraints**: 6-person engineering team with no dedicated infra engineer and no Kafka experience. The solution must be deployable within 2 weeks and fit a modest budget.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives (consumer groups, message acknowledgement, and persistence) to solve the current failures while fitting the team's operational capacity.

1. **Operational Simplicity**: We already run Redis in production for sessions and rate limiting. Adding Streams requires zero new infrastructure overhead, meeting the 2-week delivery constraint and avoiding the need for a dedicated infra engineer.
2. **Throughput & Latency**: With a peak of 500 req/s (scaling to 5,000 req/s), Redis's in-memory nature easily handles the load with sub-millisecond latency, whereas Kafka would introduce significant operational complexity for the same volume.
3. **Ordering & Consumer Groups**: Redis Streams supports consumer groups, allowing us to distribute notifications across multiple workers while maintaining ordering per stream.
4. **Exactly-Once Semantics**: While neither system provides "magic" exactly-once delivery over the wire, Redis Streams allows us to implement the required semantics for billing events by using the unique Message ID as an idempotency key in our PostgreSQL database.
5. **WebSocket Integration**: Redis is natively suited for the upcoming WebSocket requirement (Pub/Sub or Streams), allowing a unified data layer for both async processing and real-time pushes.

## Consequences
### Pros
- **Immediate Velocity**: No new software to install or manage; utilizes existing Redis instance.
- **Low Latency**: Minimal overhead for producing and consuming messages.
- **Unified Stack**: Simplifies the architecture by using one tool for caching, rate limiting, and messaging.
- **Ease of Migration**: Low risk of failure during the 2-week rollout.

### Cons
- **Memory Constraints**: Unlike Kafka's disk-based storage, Redis Streams consume RAM. We must implement a `XMAXLEN` policy to cap stream sizes to prevent OOM (Out-of-Memory) events.
- **Durability Trade-off**: While AOF (Append Only File) provides persistence, it is generally less durable than Kafka's distributed commit log. However, for this scale and use case, the trade-off is acceptable.

## Alternatives Considered
### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity**: Kafka requires Zookeeper (or KRaft) and significant tuning for JVM, memory, and disk I/O. The team has no Kafka experience and no dedicated infra engineer to manage a cluster.
- **Cost**: A managed solution (Confluent Cloud) exceeds the modest budget, and self-hosting would violate the 2-week setup constraint.
- **Overkill for Scale**: Kafka is designed for millions of messages per second and massive retention. At 5,000 req/s, the overhead of Kafka provides no tangible benefit over Redis Streams but adds significant fragility to the team's operational model.
- **Resource Heavy**: Kafka's footprint is substantially larger than Redis, which is already integrated into the environment.
