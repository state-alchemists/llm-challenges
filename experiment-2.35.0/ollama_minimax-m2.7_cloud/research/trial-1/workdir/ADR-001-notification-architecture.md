# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

### The Problem

The notification module (email + webhooks) currently executes synchronously inside the Flask HTTP request cycle. This causes:

- **Request timeouts**: Average latency 800ms, spiking to 8s at peak — users experience slow task updates
- **Silent failures**: Provider downtime results in dropped notifications with no retry
- **Cascading failures**: A slow webhook endpoint caused connection pool exhaustion twice, taking down unrelated features
- **No delivery guarantees**: Billing-critical events ("trial expired", "payment failed") have no exactly-once guarantee

### Scaling Requirements

We need to handle:
- Async processing decoupled from HTTP responses
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where required
- Real-time WebSocket push notifications within 2 quarters
- 10x traffic growth (500 req/s → 5,000 req/s peak) without re-architecting

### Constraints

- Team: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already running in production for sessions and rate limiting
- No Kafka experience on the team
- Migration window: 2 weeks maximum before delivering value
- Budget: modest; cannot afford Confluent Cloud at full scale
- Exactly-once semantics required for billing notifications

---

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams is the correct choice given our constraints. It meets all functional requirements, leverages our existing operational expertise, and can be implemented within the 2-week migration window without additional infrastructure complexity or cost.

---

## Technical Evaluation

### Throughput

| Broker | Sustained Throughput | Verdict for 5x-10x Growth |
|--------|---------------------|--------------------------|
| Redis Streams | ~500k–1M events/sec per node (memory-bound) | Sufficient: current peak 500 req/s × ~10 events = 5,000/sec; target 50,000/sec is still well within Redis Streams capacity |
| Apache Kafka | 1M+ events/sec partitioned across brokers | Over-provisioned for our scale; cost/complexity not justified |

### Ordering Guarantees

| Broker | Ordering Model | Notes |
|--------|---------------|-------|
| Redis Streams | Per-consumer-group, per-stream ordering via `XREADGROUP` | Sufficient: notifications for a given `notification_id` are processed in order; ordering across independent notifications is not a requirement |
| Apache Kafka | Per-partition total ordering | More strict than needed; would require careful partition key strategy to co-locate related events |

### Message Retention

| Broker | Retention | Fit for Billing Audit Trail |
|--------|-----------|------------------------------|
| Redis Streams | Bound to `MAXLEN` or `MINID`; RAM-constrained | Adequate: 7-day rolling window handles retry/backlog; billing events are persisted to PostgreSQL as source of truth before publishing to the stream |
| Apache Kafka | Disk-backed; configurable retention (hours to years) | Overkill: we already persist billing events to PostgreSQL; Kafka's long retention is not needed |

### Consumer Groups & Scaling

| Broker | Consumer Group Model | Scaling to 10x |
|--------|---------------------|----------------|
| Redis Streams | `XREADGROUP` with named consumer groups; multiple consumers per group; automatic claimed-message redistribution on consumer failure | Sufficient: horizontal scaling via adding consumers to the group; Redis Streams handles redelivery on failure |
| Apache Kafka | Partition-based; consumers map to partitions; requires rebalancing on add/remove | More powerful but requires understanding partition count, key strategy, and rebalancing behavior |

### Exactly-Once Semantics

| Broker | Guarantee | Implementation |
|--------|-----------|----------------|
| Redis Streams | At-least-once (ack-based) + application-level dedup | Billing event deduplication: embed `event_id` in message payload; consumers maintain a Redis SET of processed IDs with TTL; reject duplicates. This is the standard pattern and works correctly. |
| Apache Kafka | Exactly-once via Kafka Transactions (producer + consumer idempotent) | Adds significant complexity: transactional producer overhead, offset management, and the same deduplication concern at the consumer level still exists |

### Operational Complexity

| Dimension | Redis Streams | Apache Kafka |
|-----------|---------------|--------------|
| Infrastructure added | None (Redis already running) | New: ZooKeeper or KRaft, broker management, replication factor, log compaction |
| Setup time | 1–3 days: `XADD`, `XREADGROUP`, `XACK` patterns are familiar from Redis basics | 1–2 weeks minimum: cluster design, partition strategy, retention policy, monitoring, alert thresholds |
| Team expertise | Existing Redis knowledge transferable | No Kafka experience; learning curve significant under time pressure |
| Failure modes | Well-understood Redis failure modes; `WATCH` conflicts, memory pressure | Broker down = consumer lag = backpressure; under-replicated partitions; leader election; offset management bugs |
| Monitoring | Existing Redis monitoring extends easily | New tooling: consumer lag metrics, partition health, replication status, ISR violations |

---

## Consequences

### Benefits of Redis Streams

1. **No new infrastructure**: We extend our existing Redis deployment, which the team already operates and monitors.
2. **Fast migration**: The 2-week constraint is achievable. `XADD`/`XREADGROUP`/`XACK` patterns are straightforward; sample implementations exist in the Python/Redis ecosystem.
3. **Operational familiarity**: The same Redis instance used for sessions can host streams; monitoring, backup, and recovery procedures already exist.
4. **Sufficient throughput**: 500k–1M events/sec per node comfortably handles 10x growth with room to spare.
5. **WebSocket integration**: Redis Pub/Sub (or the same Redis instance) pairs naturally with WebSocket push notification requirements planned for Q2.
6. **Cost**: No additional managed service cost; self-hosted Redis is already in the EC2 footprint.

### Drawbacks and Mitigations

1. **RAM-constrained retention**: Rolling 7-day window is RAM-bound. If memory fills, oldest messages drop.
   - **Mitigation**: Size the Redis instance appropriately (`MAXLEN` trimming + `OBJECT MEMORY USAGE` monitoring). For billing, we persist to PostgreSQL *before* publishing to the stream — the DB is the durable record, not the stream.
2. **No native exactly-once**: Redis Streams guarantees at-least-once, not exactly-once.
   - **Mitigation**: Application-level deduplication via `event_id` in a Redis SET with TTL. This is the same pattern Kafka consumers implement for true exactly-once; the complexity is equivalent.
3. **Single-node bottleneck under extreme scale**: A single Redis instance could become a bottleneck above ~100k events/sec.
   - **Mitigation**: Redis Cluster mode (sharding) can be introduced when needed; the streams API supports `XREADGROUP` across multiple streams via `XREAD`. However, we will not need this for the 10x target.
4. **No native dead-letter queue**: Failed messages after max retries need a DLQ pattern.
   - **Mitigation**: Implement a secondary stream `notifications.dlq` where messages are moved after max retry attempts; a separate consumer alerts on DLQ buildup.

### Comparison to Kafka

Kafka would provide marginally stronger ordering guarantees and native exactly-once transactions, but these benefits do not outweigh the operational burden for our team size and timeline. Redis Streams meets all stated requirements; Kafka would be over-engineering at this stage.

---

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for event streaming and would comfortably handle our use case at any scale. Specific strengths:

- **Native exactly-once semantics** via Kafka Transactions
- **Disk-backed retention** (weeks/months) with replay capability
- **Proven at massive scale** (LinkedIn, Netflix, Confluent-managed)
- **Rich ecosystem**: Kafka Connect, Schema Registry, KSQL/Flink integration

However, we reject Kafka for the following reasons:

1. **No team experience**: A 6-person team with no Kafka expertise, under a 2-week delivery constraint, cannot safely absorb cluster management, partition strategies, replication factor tuning, and monitoring setup.
2. **Operational overhead**: Kafka requires ZooKeeper (or KRaft in newer versions) management, broker health monitoring, ISR (in-sync replica) tracking, log retention enforcement, and partition rebalancing procedures. This is a dedicated infrastructure engineer's job.
3. **Cost**: Self-hosting Kafka on EC2 requires at minimum 3 brokers for HA, plus monitoring infrastructure. Managed Confluent Cloud at our scale is not in the modest budget.
4. **Over-provisioned**: Our peak throughput target is ~50,000 events/sec. Redis Streams handles this comfortably on a single instance. Kafka's throughput advantage is irrelevant at our scale.
5. **Same deduplication burden remains**: Even with Kafka's exactly-once transactions, the consumer still needs idempotent processing for billing events — the application-level deduplication requirement is not eliminated.

**Kafka is the correct choice for a larger team, longer timeline, or higher scale.** If our traffic grows 100x beyond the 10x target, we should revisit this decision and consider Kafka (or a managed streaming service like AWS Kinesis or Confluent Cloud at entry tier).

---

## Recommendation Summary

| Requirement | Redis Streams | Kafka |
|-------------|---------------|-------|
| Async decoupled processing | ✓ | ✓ |
| Retry with exponential backoff | ✓ | ✓ |
| At-least-once delivery | ✓ (XACK) | ✓ |
| Exactly-once for billing | ✓ (dedup via event_id) | ✓ (transactions, but same dedup needed) |
| 10x traffic growth | ✓ | ✓ |
| WebSocket push (Q2) | ✓ (Redis Pub/Sub) | Requires separate system |
| Setup ≤ 2 weeks | ✓ | ✗ (too complex) |
| No new infrastructure | ✓ | ✗ |
| Team has expertise | ✓ (existing Redis) | ✗ |
| Modest budget fit | ✓ | ✗ |

**Decision: Redis Streams.**

Implementation should proceed with:
1. A `notifications.pending` stream for outgoing email/webhook jobs
2. A `notifications.dlq` stream for messages exceeding max retry attempts
3. Application-level deduplication using `event_id` SET with TTL for billing events
4. Worker process using `XREADGROUP` with `BLOCK` for efficient polling
5. Exponential backoff via `XCLAIM` with `MIN-IDLE-TIME` for redelivery delays
