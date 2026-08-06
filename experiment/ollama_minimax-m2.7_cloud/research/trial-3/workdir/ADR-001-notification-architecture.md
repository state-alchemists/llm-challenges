# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

The notification module currently executes synchronously inside the HTTP request cycle, causing request timeouts (average 800ms, spikes to 8s), silent failures with no retry, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical events. We need to decouple notifications from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery for billing events (exactly-once where feasible), and handle 10x traffic growth.

**System scale**: ~2M tasks/month, 500 req/s peak, 85K MAU, 4 web servers on AWS.

**Team constraints**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer, no Kafka experience today. Redis is already in production for session storage and rate limiting. Setup/migration must deliver value within 2 weeks. Budget is modest — managed Confluent Cloud at full scale is not affordable. Exactly-once semantics are required for billing notifications.

**Future requirements**: WebSocket push notifications within 2 quarters.

---

## Decision

**Choose Redis Streams.**

Redis Streams is the correct choice given the team's operational constraints, the existing Redis footprint, the 2-week delivery deadline, and the scale requirements. It satisfies the functional requirements (async decoupling, retry, dead-letter queue, at-least-once delivery) while requiring zero new infrastructure and minimal operational overhead.

---

## Consequences

### Pros

1. **No new infrastructure.** Redis is already running. The team deploys, monitors, and maintains one fewer system.
2. **Operational simplicity.** Redis Streams uses standard Redis commands (`XADD`, `XREADGROUP`, `XACK`, `XRANGE`). No new cluster topology, no partition balancing, no broker-specific CLI tooling to learn.
3. **Fast onboarding.** No Kafka experience needed. A mid-level engineer can read the full Streams documentation in an afternoon and be productive within days, not weeks.
4. **Sub-millisecond latency.** Redis operates in-memory. Notification dispatch latency is dominated by the external provider (email/webhook), not the broker.
5. **Consumer groups with ACK semantics.** `XREADGROUP` + `XACK` provides at-least-once delivery with redelivery on failure. A dead-letter stream (`notifications.dlq`) captures messages that exceed retry limits.
6. **Exponential backoff via application logic.** The consumer group loop (blocking read → process → ACK) wraps processing in a retry loop with configurable backoff. Failed messages go to the DLQ after N attempts.
7. **Sufficient throughput.** 500 req/s peak is well within Redis Streams' performance envelope (100K–500K msgs/s on commodity AWS instances). 10x growth (5,000 req/s) remains manageable on properly sized infrastructure.
8. **Exactly-once for billing notifications.** Achieved via deduplication: producers assign a stable idempotency key (e.g., `notification:{event_type}:{entity_id}:{timestamp_bucket}`), and consumers check a Redis set before processing. This is a well-understood pattern with low overhead.
9. **Existing Redis expertise.** The team already operates Redis. Configuration, monitoring, persistence (`RDB`/`AOF`), and failure modes are familiar.
10. **WebSocket readiness.** Redis Pub/Sub or Streams can fan out to WebSocket servers. A unified Redis footprint simplifies the real-time push architecture planned for 2 quarters out.

### Cons

1. **Message retention is ID-space limited.** Redis Streams uses 64-bit timestamps as IDs; retention is bounded by `MAXLEN` (capped at ~232 entries per stream in practice due to radix tree memory efficiency) or by time via `MAXLEN ~`. For audit-logging use cases that require multi-day retention, explicit `MAXLEN` trimming is needed. This is manageable for a notification system where messages are processed and acknowledged quickly.
2. **No native partitioning.** Kafka distributes load across topic partitions. Redis Streams uses consumer groups within a single stream; horizontal scaling is achieved by adding consumers to groups, but there is no automatic load balancing across multiple streams. For 10x growth, stream sharding (multiple stream keys) would need to be managed by application logic.
3. **Exactly-once requires application-layer work.** Kafka's transactional producer API provides exactly-once out of the box. Redis Streams provides at-least-once; exactly-once must be implemented via idempotency keys (documented above). This is a known pattern but adds code.
4. **Blocking read semantics.** `XREADGROUP BLOCK` is a blocking operation. Misconfigured consumers can hold connections open indefinitely. Consumer timeouts must be set carefully.
5. **No native message replay by offset.** Kafka's offset model is more flexible for replaying from a specific point. Redis Streams replays by ID range (`XRANGE`), which works for the DLQ reprocessing case but is less ergonomic.
6. **Limited monitoring ecosystem.** Kafka has mature tooling (Kafka Manager, CMAK, Confluent Control Center). Redis Streams monitoring relies on `XINFO`, `XLEN`, `XPENDING`, and third-party Redis exporters (e.g., Redis Exporter for Prometheus). This is sufficient but less batteries-included.
7. **Persistence trade-off.** If Redis is restarted with `AOF` persistence, in-flight messages that were not yet ACK'd may be lost. This is mitigated by using `appendfsync everysec` or `always`, and by sizing `maxmemory` appropriately. This is an operational concern the team must understand.

---

## Alternatives Considered

### Apache Kafka

**Why it was considered.** Kafka is the industry standard for event streaming: 1M+ messages/second throughput, true partitioned topics with ordered per-partition delivery, exactly-once semantics via the Transactions API, configurable message retention (hours to years), and a rich ecosystem of connectors, schema registry, and monitoring tooling. It is the correct choice for teams with dedicated platform/infrastructure engineers and Kafka operational experience.

**Why it was rejected given our constraints.**

1. **No Kafka experience on the team.** The learning curve is steep. Understanding topic partitions, replication factor, consumer group rebalancing, retention sizing, and JVM-based broker tuning requires time the 2-week deadline does not allow. A misconfigured Kafka cluster (e.g., default partition count, insufficient replication) can exhibit severe performance degradation or data loss silently.
2. **Operational complexity.** Kafka requires ZooKeeper (or KRaft in newer versions) for metadata management, separate JVM heap sizing, log directory partitioning, and broker replacement procedures. With no dedicated infrastructure engineer, this operational surface is not manageable at the required reliability level.
3. **Budget.** Managed Kafka (Confluent Cloud, AWS MSK) at the throughput and retention levels required for billing-critical exactly-once notifications involves meaningful cost at scale. Self-hosted Kafka on EC2 adds 3–4 additional instances (brokers + ZooKeeper), increasing operational burden and cost.
4. **Setup timeline.** A production-ready Kafka deployment — including broker configuration, topic design (partition count, replication factor, retention policy), producer/consumer library integration, and DLQ handling — realistically takes 3–4 weeks for a team with prior experience. For a team learning from scratch, 2 weeks produces a fragile system, not a production one.
5. **Over-engineering.** 500 req/s (growing to 5,000 req/s) does not require Kafka's throughput ceiling. Redis Streams comfortably handles this with a fraction of the operational surface. Kafka is the right tool for high-volume event sourcing, log aggregation, or microservice event mesh at 100K+ req/s — this system does not yet operate at that scale.
6. **Same exactly-once problem.** Even Kafka's exactly-once semantics require careful implementation (idempotent producers + transactional consumers). The gap between "Kafka supports exactly-once" and "your application achieves exactly-once" is non-trivial and requires the same deduplication patterns Redis Streams requires.

**Conclusion:** Kafka is the correct long-term architecture if the team grows a platform engineering function, the notification system becomes an event mesh serving multiple downstream consumers, or throughput consistently exceeds ~50K req/s. For the current 2-week deadline, 6-person team, and 10x growth target, Redis Streams is the right tool now. The architecture can be re-evaluated at that scale.
