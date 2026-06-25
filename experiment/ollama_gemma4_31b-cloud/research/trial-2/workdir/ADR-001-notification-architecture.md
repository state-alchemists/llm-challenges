# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system operates synchronously within the HTTP request cycle of our Python/Flask monolith. This has led to critical production issues:
- **Performance Degradation**: Average response times of 800ms, spiking to 8s, causing request timeouts.
- **Reliability Gaps**: Lack of retry mechanisms leads to silent failures of emails and webhooks.
- **System Instability**: Connection pool exhaustion caused by slow external webhook endpoints has triggered cascading failures across unrelated features.
- **Consistency Issues**: Billing-critical notifications (e.g., "payment failed") lack delivery guarantees.

**Constraints:**
- **Team**: 6 engineers; no dedicated DevOps/Infrastructure role.
- **Knowledge**: Zero internal experience with Apache Kafka.
- **Infrastructure**: Already running Redis for session/rate limiting.
- **Timeline**: Maximum 2 weeks for setup/migration to deliver immediate value.
- **Budget**: Modest; managed Confluent Cloud is currently cost-prohibitive.
- **Requirements**: Must support 10x growth (5,000 req/s peak), exactly-once semantics for billing, and future WebSocket integration.

## Decision
We will implement **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the optimal balance between the required technical guarantees and the team's operational capacity.

1. **Operational Simplicity**: We already maintain Redis in production. Adopting Redis Streams requires no new infrastructure software, no new monitoring stacks, and no specialized knowledge, fitting within the 2-week delivery window.
2. **Throughput & Performance**: At 500 req/s (and 10x growth to 5,000 req/s), Redis Streams easily handles the load with sub-millisecond latency, removing the blocking overhead from the Flask request cycle.
3. **Consumer Groups**: Redis Streams' consumer group feature allows us to scale the notification workers horizontally and ensures that each message is processed by only one worker in a group, providing the necessary foundation for at-least-once delivery.
4. **Exactly-Once Semantics**: While neither system provides "true" exactly-once delivery to external third-party APIs (emails/webhooks), we will achieve effectively exactly-once processing for billing events by combining Redis Streams' acknowledgment (`XACK`) with an idempotency layer in PostgreSQL (recording processed event IDs).
5. **Future Proofing**: Redis's pub/sub and stream capabilities align perfectly with the upcoming requirement for real-time WebSocket push notifications.

## Consequences
### Pros
- **Immediate Velocity**: Low barrier to entry; development can start immediately using existing Redis instances.
- **Reduced Resource Overhead**: Avoids the significant RAM and CPU overhead of a JVM-based Kafka cluster.
- **Unified Tooling**: Maintains a slim infrastructure footprint, critical for a team without a dedicated infra engineer.
- **Decoupling**: Successfully moves notification logic out of the request cycle, eliminating the risk of cascading failures from slow external APIs.

### Cons
- **Memory Bound**: Redis stores streams in memory. While we can use `MAXLEN` to cap stream size, we must monitor memory usage more closely as throughput grows.
- **Persistence Trade-off**: While Redis provides AOF/RDB persistence, it is not as durable as Kafka's distributed commit log. This is acceptable given our use of PostgreSQL as the primary source of truth for billing events.

## Alternatives Considered
### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity**: Introducing Kafka would require managing a Zookeeper or KRaft quorum, configuring partitions, and tuning JVM settings. This is unrealistic for a 6-person team with no Kafka expertise.
- **Infrastructure Cost**: The budget cannot support managed services like Confluent, and self-hosting would divert significant engineering effort away from product features.
- **Over-Engineering**: Kafka's massive scale capabilities (millions of events/sec) far exceed our 10x growth target. The "cost of carry" for Kafka's complexity outweighs its benefits at our current and projected scale.
