# ADR-001: Notification Subsystem — Redis Streams vs. Apache Kafka

## Status

Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, ~500 req/s peak) processes notifications synchronously inside the HTTP request cycle. This causes request timeouts (800ms avg, 8s spikes), silent delivery failures with no retry, cascading connection-pool exhaustion, and no delivery guarantees for billing-critical events.

We need to decouple notifications from the request cycle with an async message stream that supports:

- **Retry with exponential backoff** for failed deliveries
- **At-least-once delivery** for all notifications; **exactly-once where feasible** for billing events
- **Consumer groups** so multiple workers can share processing
- **Dead-letter handling** for permanently failed messages
- **10x traffic growth** without re-architecting (~5,000 req/s peak)
- **Real-time WebSocket push** within two quarters (fan-out to many connected clients)
- **Delivery within 2 weeks** of starting migration

Key constraints: 6-person team (no dedicated infra engineer), no Kafka experience, Redis already in production, modest budget.

## Decision

**Choose Redis Streams as the notification subsystem's message broker.**

Redis Streams provides consumer groups, persistent append-only logs, and at-least-once delivery — the core primitives we need — while fitting the team's existing skill set, infrastructure, and time budget. We layer an application-level idempotency key on billing notifications to achieve effective exactly-once semantics, rather than relying on Kafka's transactional producer/consumer protocol, which our team has no experience operating.

## Consequences

### Pros

- **Zero new infrastructure.** Redis is already running in production. No new cluster to provision, monitor, or patch. The 2-week deadline is feasible because we write consumer code against an existing endpoint, not stand up a distributed system first.
- **Fits team capacity.** The team knows Redis operational patterns (memory management, persistence, replication). No one has Kafka experience; adopting it means ramp-up on broker configuration, topic design, partition strategy, and ZooKeeper/KRaft — all under the pressure of a live incident-driven migration.
- **Consumer groups.** Redis 5+ supports XREADGROUP, XPENDING, and XCLAIM — the same logical model as Kafka consumer groups. Multiple workers can claim messages, track pending deliveries, and re-claim stalled work, enabling retry with exponential backoff.
- **Sufficient throughput.** Redis Streams handles 10M+ commands/sec on a single node for simple stream writes. Our 10x scaling target (~5,000 notifications/sec peak) is well within capacity, even with overhead for consumer-group acknowledgements.
- **Low latency.** Sub-millisecond message delivery suits the upcoming WebSocket push requirement, where fan-out to thousands of connected clients demands low per-message overhead.
- **Dead-letter via application logic.** After N retries, messages move to a dedicated `notifications:dead-letter` stream. Simple, observable, and consistent with our existing Redis-backed rate-limiting patterns.
- **Modest budget impact.** A single Redis node (or a small HA pair) costs a fraction of a managed Kafka deployment. Self-hosted Kafka on EC2 shifts cost to engineering time, which is the tighter constraint.

### Cons

- **No native exactly-once semantics.** Redis Streams provides at-least-once delivery. We implement effective exactly-once for billing notifications via idempotency keys (a deterministic notification ID stored in a Redis HSET, checked before delivery). This is correct but requires application discipline — every billing notification handler must implement the check-and-emit pattern.
- **Memory-bound retention.** Redis stores streams in memory (with optional AOF/RDB persistence). Message retention is bounded by memory, not disk. At 10x scale (~5k msg/sec), a 7-day retention window is ~3 billion messages — too large for RAM. We mitigate with `MAXLEN` trimming (e.g., keep last 100k messages per stream) and persist critical events to PostgreSQL immediately on consumption, making the stream a short-lived processing buffer rather than a long-term event log.
- **No native partitioning.** Kafka topics partition automatically, distributing load across brokers. Redis Streams are single-key data structures living on one shard. At our scale this is acceptable (single-shard throughput exceeds our needs), but fan-out to many WebSocket-connected users will require application-level sharding of stream keys if per-key throughput becomes a bottleneck.
- **Operational risk of single Redis dependency.** Redis becomes a single point of failure for both sessions/rate-limiting and notifications. We mitigate by running Redis in a primary-replica failover configuration (already planned) and isolating notification streams to a dedicated Redis instance once volume justifies it.
- **Limited ecosystem tooling.** Kafka Connect, Schema Registry, and Kafka Streams have no Redis equivalents. If we later need complex stream processing (joins, windowed aggregations), we build it in application code or introduce a secondary system.

## Alternatives Considered

### Apache Kafka

Kafka is the stronger choice in absolute terms: durable disk-based retention, partitioned topics for horizontal scaling, native exactly-once semantics (idempotent producer + transactional consumer), a rich ecosystem (Connect, Schema Registry, Kafka Streams), and battle-tested operation at far higher throughput than we require.

We rejected it for this decision because:

1. **Operational complexity exceeds team capacity.** A 6-person team with no Kafka experience and no dedicated infrastructure engineer cannot safely operate a Kafka cluster in production within 2 weeks. Managed Confluent Cloud removes the operations burden but conflicts with our budget constraint at scale.
2. **Time-to-value.** Kafka requires topic design, partition planning, producer/consumer configuration, monitoring, and on-call playbooks before the first notification moves asynchronously. Redis Streams requires a `XADD` call and a consumer script — against infrastructure we already run.
3. **Our throughput needs don't require it.** Kafka's architectural advantages (partitioned parallelism, disk-based long retention) matter at throughputs and retention windows orders of magnitude beyond our 10x scaling target. Redis Streams on a single node comfortably handles our projected load.
4. **Migration path exists.** If we outgrow Redis Streams (e.g., needing multi-day event retention at high volume, cross-service event sourcing, or Kafka-based stream processing), we can migrate individual streams to Kafka using a dual-write period — the consumer-group abstraction is similar enough that worker code structure transfers directly.

The trade-off is clear: Kafka is the superior message broker, but Redis Streams is the superior choice *for this team, at this scale, with these constraints*. We optimize for shipping a working notification system in 2 weeks, not for theoretical scaling headroom we won't use for years.