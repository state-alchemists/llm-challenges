# ADR-001: Notification Subsystem Message Broker Selection

## Status

Proposed

## Context

The current notification system runs synchronously inside the HTTP request cycle, causing request timeouts (average 800ms, spikes to 8s), silent failures with no retry, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical notifications.

**Requirements:**
- Decouple notifications from the HTTP request cycle
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- WebSocket push notifications within 2 quarters
- Handle 10x traffic growth (from ~500 req/s peak to ~5,000 req/s)

**Constraints:**
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already running in production for session storage and rate limiting
- No Kafka experience on the team
- 2-week maximum setup/migration window
- Modest budget (Confluent Cloud at full scale is not affordable)
- Exactly-once semantics required for billing notifications

**Scale baseline:**
- 85,000 monthly active users
- ~2M tasks created per month
- Peak: ~500 req/s during business hours
- Target: ~20M tasks/month, ~5,000 req/s peak after 10x growth

## Decision

**Chosen option: Redis Streams**

Redis Streams is selected as the message broker for the notification subsystem. This decision is driven by the team's existing Redis expertise, operational simplicity, and sufficient throughput capacity for current and projected loads.

### Justification

**1. Throughput Capacity**
Redis Streams handles 100,000+ messages per second on commodity hardware, far exceeding the 5,000 req/s peak target. The current 500 req/s and 10x growth scenario are well within Redis Streams' capabilities. Kafka would provide millions of messages per second capacity, which is unnecessary headroom for this workload.

**2. Operational Simplicity**
The team already operates Redis in production for session storage and rate limiting. This means:
- No new infrastructure to learn, monitor, or debug
- Existing Redis operational knowledge transfers directly
- No need to manage ZooKeeper/KRaft, broker configuration, or partition leadership
- Redis Streams uses standard Redis clients (`redis-py`) the team already uses

Kafka's operational complexity includes broker replication factor, partition balancing, consumer group offset management, and retention policies. For a 6-person team with no Kafka experience, this creates significant risk within the 2-week constraint.

**3. Time-to-Value**
Redis Streams can be integrated incrementally. The team can:
- Reuse existing Redis connections and client libraries
- Add a single new dependency (`redis>=7.0` for Streams commands)
- Migrate synchronously-handled notifications in phases

Kafka requires broker provisioning, topic configuration, consumer group setup, and operational runbooks before delivering any value.

**4. Exactly-Once Semantics**
Both Kafka and Redis Streams require producer idempotency + consumer deduplication for exactly-once delivery. Redis Streams provides:
- `XADD` with client-generated message IDs for idempotent producers
- `XREADGROUP` with `XACK` for consumer acknowledgment
- Consumer-side deduplication using message IDs or content hashes

This is sufficient to guarantee exactly-once for billing notifications when combined with idempotency keys stored in PostgreSQL.

**5. Message Retention**
Redis Streams supports message retention up to the stream's `MAXLEN` or `MINID` policy. With memory allocation for stream entries, this meets the "replay within 24-48 hours" requirement typical for notification systems. Kafka's configurable retention (hours to weeks) is not needed at this scale.

**6. Consumer Groups**
Redis Streams `XREADGROUP` provides consumer group semantics equivalent to Kafka consumer groups:
- Multiple consumers share work within a group
- Failed consumer reassignment via `XCLAIM`
- Pending entry list (`XPENDING`) for tracking in-flight messages

**7. Cost**
Redis can run on existing infrastructure (EC2 instance already serving session storage). Kafka would require dedicated broker instances, increasing infrastructure costs.

## Consequences

### Pros of Redis Streams

| Benefit | Impact |
|---------|--------|
| Operational familiarity | Team can operate and debug with existing Redis knowledge |
| Fast integration | <1 week to have working prototype; 2-week deadline achievable |
| Sufficient throughput | 100k+/sec capacity vs. 5k/sec needed — 20x headroom |
| Consumer groups | Full support for shared work, reassignment, and dead-letter handling |
| Replay capability | `XREAD` from specific ID enables replay for recovery |
| Cost efficiency | No new infrastructure; uses existing Redis instance |
| WebSocket readiness | Redis Pub/Sub can complement Streams for real-time push |

### Cons of Redis Streams

| Drawback | Mitigation |
|----------|------------|
| Memory-based storage | Configure `MAXLEN` policy to bound memory; stream entries are small |
| Single-instance bottleneck (if not clustered) | Redis Cluster mode available for horizontal scaling; current scale doesn't require it |
| No native compaction | Use consumer-side deduplication tables for deduplication use cases |
| Smaller ecosystem | Fewer third-party integrations than Kafka; not a concern for internal use |
| Persistence vs. Kafka | AOF/RDB provides durability; sufficient for notification workloads |

### Risks

1. **Memory pressure**: Stream entries consume RAM. Mitigation: enforce `MAXLEN~` (approximate trimming) to cap memory usage regardless of traffic spikes.

2. **Single point of failure**: Redis Streams on a single instance could lose messages if the instance fails. Mitigation: enable AOF persistence with `appendfsync everysec` for sub-second durability; upgrade to Redis Cluster for HA if needed.

3. **Scaling past 10x**: If growth exceeds 10x projections, Redis Streams may require cluster mode sharding. Mitigation: architecture supports horizontal scaling; re-evaluate at that time.

## Alternatives Considered

### Apache Kafka

**Why it was rejected:**

1. **Operational complexity exceeds constraints**: Kafka requires managing brokers, ZooKeeper/KRaft, partition replication, and consumer group offset storage. A 6-person team with no Kafka experience cannot safely operate Kafka within the 2-week window without dedicated infrastructure support.

2. **Over-engineering for the workload**: The 5,000 req/s peak target is 20x smaller than Kafka's typical minimum viable deployment. Running Kafka for this throughput is like using a cargo ship to deliver a package across town.

3. **Longer time-to-value**: Kafka requires broker provisioning, topic creation with partition counts, consumer group configuration, and operational runbooks before delivering any notification value. This risks missing the 2-week deadline.

4. **Budget incompatibility**: Self-hosted Kafka on EC2 requires significant instance resources (typically 3+ brokers for HA). Confluent Cloud pricing at this scale is not within modest budget constraints.

5. **Unnecessary features**: Kafka's strengths (million-message retention, log compaction, stream processing) are not required for the notification use case.

### Comparison Table

| Criteria | Redis Streams | Apache Kafka |
|----------|---------------|--------------|
| Throughput capacity | 100k+/sec | Millions/sec |
| Operational complexity | Low (team knows Redis) | High (new paradigm) |
| Setup time | <1 week | 2-4 weeks |
| Exactly-once | Yes (with deduplication) | Yes (transactions) |
| Consumer groups | Yes | Yes |
| Message retention | Bounded by memory/MAXLEN | Hours to weeks configurable |
| Team expertise | Existing | None |
| Infrastructure cost | Uses existing Redis | New dedicated instances |
| WebSocket complement | Native Pub/Sub | Requires separate system |

## Recommendation

**Proceed with Redis Streams** as the message broker for the notification subsystem. The decision balances team capabilities, time constraints, and technical requirements:

- **Throughput**: Redis Streams' 100k+/sec capacity covers the 5,000 req/s target with 20x headroom.
- **Team fit**: Leverages existing Redis expertise; no new infrastructure paradigm to learn.
- **Timeline**: Achievable within the 2-week constraint.
- **Cost**: Uses existing Redis infrastructure.
- **Exactly-once**: Achievable via producer idempotency + consumer deduplication.

Kafka is the correct choice for systems requiring millions of events/second, multi-day retention, log compaction, or distributed stream processing. None of these apply to the notification subsystem's requirements and constraints.

If at any point the system exceeds 50,000 req/s sustained or requires Kafka's specific features, re-evaluate at that time. The notification architecture can migrate to Kafka in the future if justified by scale.
