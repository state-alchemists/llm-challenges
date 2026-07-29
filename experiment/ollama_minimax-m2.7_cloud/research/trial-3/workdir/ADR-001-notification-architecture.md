# ADR-001: Notification Subsystem Message Queue Architecture

## Status

**Proposed**

## Context

### The Problem

Our notification module sends emails and webhooks synchronously within the HTTP request cycle. This has caused:

1. **Request timeouts**: Average latency 800ms, spikes to 8s during peak hours (500 req/s)
2. **Silent failures**: Dropped notifications when email providers or webhook endpoints are unavailable — no retry, no dead-letter queue
3. **Cascading failures**: Two incidents where a slow webhook endpoint exhausted the connection pool, destabilizing unrelated features
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, but the current system cannot guarantee this

### Scaling Target

- Decouple notifications from the HTTP request cycle (async processing)
- Support retry with exponential backoff
- Guarantee at-least-once delivery for billing events; exactly-once where feasible
- Add real-time WebSocket push notifications within 2 quarters
- Handle 10x traffic growth (5,000 req/s peak) without re-architecting

### Constraints

| Constraint | Implication |
|---|---|
| 6-person engineering team (3 senior, 3 mid-level), no dedicated infra engineer | Cannot absorb high operational complexity |
| Redis already in production (session storage, rate limiting) | Infrastructure cost is sunk; leverage existing investment |
| No Kafka experience on the team | Learning curve is a real cost, not just a FUD factor |
| 2-week maximum setup/migration before delivering value | Operational overhead must be low from day one |
| Modest budget; cannot afford Confluent Cloud at full scale | Self-managed Kafka means significant infra engineering time |
| Exactly-once semantics required for billing notifications | Must be a first-class capability, not a hack |

### Load Analysis

| Metric | Current | 10x Target |
|---|---|---|
| Monthly active users | 85,000 | 850,000 |
| Tasks created/month | ~2M | ~20M |
| Peak request rate | 500 req/s | 5,000 req/s |
| Notification rate (est. 1-3 per task) | ~1,500-4,500 notifications/min at peak | 15,000-45,000 notifications/min at peak |

**Throughput requirement at 10x**: approximately **75-225 notifications/second** at peak (assuming 3 notifications per task, 5,000 req/s × 3 = 15,000 notifications/min = 250/sec). This is well within single-node Redis Streams capacity (~100,000+ msg/sec).

## Decision

**Choose Redis Streams.**

Redis Streams provides all required capabilities — consumer groups, at-least-once delivery with retry, ordered delivery per consumer group, and a viable path to exactly-once semantics — while operating within our team's operational constraints. The existing Redis infrastructure eliminates setup time and marginal cost.

### Why Redis Streams Satisfies the Requirements

1. **Async processing**: Producers `XADD` to a stream; consumers `XREADGROUP` from consumer groups. Full decoupling from the HTTP cycle.

2. **Retry with exponential backoff**: Implemented in the consumer using `XACK` after successful processing and tracking failed messages with `XRANGE` / `XPENDING`. Dead-letter queue via a separate `notifications.dlq` stream.

3. **At-least-once delivery**: `XREADGROUP` with `ACK` via `XACK`. Unacknowledged messages remain in the Pending Entries List (PEL) and are redelivered.

4. **Exactly-once for billing**: Achieved via idempotent consumers — each message carries a dedup key (notification ID); consumers check a Redis SET before processing and `XACK` only after successful commit.

5. **WebSocket push within 2 quarters**: Redis Streams integrates naturally with Redis Pub/Sub for fan-out to WebSocket servers. The same Redis cluster serves both workloads.

6. **10x traffic without re-architecting**: Redis Streams on a properly resourced instance handles 100K+ msg/sec. Sharding (Redis Cluster mode) is available when needed, though unlikely within the 10x horizon.

## Consequences

### Benefits of Redis Streams

| Benefit | Detail |
|---|---|
| **Minimal operational overhead** | Redis is already monitored, backed up, and familiar to the team. No new system to operate. |
| **Days to production, not weeks** | A basic producer/consumer pipeline can be running within 2-3 days. Full migration with DLQ and retries within 1 week. |
| **No additional infrastructure cost** | Uses existing Redis instance (or a dedicated node if needed for isolation). |
| **Consumer groups are equivalent to Kafka consumer groups** | Named consumer groups with own cursor position. `XREADGROUP` blocks until messages arrive. |
| **Ordered delivery per consumer** | Within a consumer group, messages are delivered in stream order to each consumer. |
| **Native dead-letter queue support** | Separate stream for failed messages after N retries. Simple to inspect and replay. |
| **Scales to 10x with headroom** | 250 msg/sec peak requirement vs ~100K+/sec capacity leaves massive margin. |
| **WebSocket integration** | Redis Pub/Sub or Streams fan-out to multiple WebSocket servers is straightforward. |

### Risks and Drawbacks

| Risk | Severity | Mitigation |
|---|---|---|
| **Redis is primarily an in-memory store** — message retention is limited to available RAM. At high volumes, message accumulation during consumer outages could pressure memory. | Medium | Configure `MAXLEN` or `MAXLEN~` on streams to cap retention. Set consumer lag alerts. Size Redis appropriately (16-32GB is sufficient for months of buffer at our scale). |
| **No native cross-datacenter replication in open-source Redis** — if the Redis node fails, messages not yet consumed are lost unless AOF/RDB persistence + replication are configured. | Medium | Enable `appendfsync always` + replica-of configuration for a hot standby. Redis Cluster in sentinel mode provides automatic failover. |
| **Single consumer group can become a bottleneck** — if one consumer processes slowly, it slows the entire group. | Low | Use multiple independent consumer groups for different notification types (email, webhook, billing). |
| **Redis Streams is less battle-tested at extreme scale** compared to Kafka — but our scale is far below Kafka's sweet spot. | Low | The 10x target (250 msg/sec peak) is well within Redis Streams' proven capacity. Kafka would be over-engineered. |
| **Exactly-once requires idempotent consumers** — developers must implement dedup checks. | Medium | Provide a base consumer class with dedup logic; enforce via code review. This is standard practice even with Kafka's exactly-once. |

### Comparison Matrix

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| **Throughput (single node)** | ~100K-500K msg/sec | ~1-2 MB/sec per partition (limited by disk I/O) |
| **Ordering** | Per consumer group, per stream | Per partition |
| **Message retention** | RAM-bounded (configurable MAXLEN) | Disk-bounded (days to indefinite) |
| **Consumer groups** | Yes (`XREADGROUP`) | Yes (native) |
| **Exactly-once semantics** | Via idempotent consumers | Via Kafka Transactions (idempotent producer + consumer) |
| **At-least-once semantics** | Native via PEL + XACK | Native via offset commit after processing |
| **Dead-letter queue** | Separate stream (manual) | Separate topic (manual) |
| **Operational complexity** | Low | High |
| **Setup time** | 2-3 days POC, 1 week production | 2+ weeks minimum |
| **Team learning curve** | Negligible (Redis experience exists) | Significant (no Kafka experience) |
| **Infrastructure cost** | Marginal (uses existing Redis) | Significant (brokers, ZooKeeper/KRaft, monitoring) |
| **WebSocket integration** | Native Pub/Sub fan-out | Requires separate service |

## Alternatives Considered

### Apache Kafka

**Summary**: Kafka is the industry standard for event streaming at massive scale. It offers superior throughput, unlimited retention, and battle-tested exactly-once semantics via transactions. However, it does not fit our constraints.

**Why we rejected Kafka**:

1. **Operational complexity is prohibitive for a 6-person team with no dedicated infra engineer.** Kafka requires managing brokers, ZooKeeper or KRaft (in KRaft mode since Kafka 3.5+), partition leadership, replication factor, consumer group lag monitoring, and capacity planning. This is a full-time job.

2. **Two-week constraint would be violated.** A production-ready Kafka setup — even on a managed service like Amazon MSK — requires: cluster sizing, topic configuration (partition count, replication factor, retention settings), consumer group implementation with error handling and dead-letter topics, schema registry for message contracts, and monitoring dashboards. Two weeks is optimistic for a team with no prior Kafka experience.

3. **Cost.** Self-managed Kafka on EC2 requires at minimum 3 brokers for HA (m5.xlarge or larger = ~$300/month per instance = $900/month). Amazon MSK is $0.21 per broker-hour = ~$450/month minimum. This is significant against a modest budget, especially when Redis is already paid for.

4. **Over-engineering for our scale.** Kafka's sweet spot is millions of messages per second across multiple datacenters. Our 10x target is ~250 msg/sec. Kafka's minimum operational footprint is the same whether you're doing 250 or 2.5 million msg/sec.

5. **Exactly-once with Kafka still requires idempotent consumers.** Kafka transactions guarantee exactly-once *to Kafka* — but if the downstream consumer (email provider, webhook endpoint) is not idempotent, you still need dedup logic. The complexity savings are smaller than they appear.

**When Kafka would be the right choice**:
- Team size ≥ 15 with dedicated platform/infrastructure engineers
- Message throughput ≥ 100,000 msg/sec sustained
- Regulatory requirement for months/years of immutable audit log of every notification
- Multi-datacenter active-active replication requirements
- Existing Confluent Platform or Strimzi investment

### Rejected Alternative: RabbitMQ

RabbitMQ was considered briefly but rejected because:
- Classic mirrored queues do not provide the ordering guarantees we need
- Quorum queues (the modern replacement) have operational overhead similar to Kafka
- Redis Streams provides equivalent messaging semantics with our existing infrastructure
- RabbitMQ would be an additional service to operate, not a consolidation of existing assets

## Recommendation

**Implement Redis Streams for the notification subsystem.**

The architecture would be:

```
[Flask App] --> XADD notifications:email    --> [Consumer Group: email-workers]
             --> XADD notifications:webhook  --> [Consumer Group: webhook-workers]
             --> XADD notifications:billing --> [Consumer Group: billing-workers]

Failed messages after 3 retries --> XADD notifications:dlq

WebSocket fan-out via Redis Pub/Sub (separate channel per user)
```

This delivers value within the 2-week constraint, uses existing infrastructure, and scales to 10x traffic comfortably. Exactly-once for billing is achieved by marking each billing notification with a UUID and checking against a Redis SET before processing — a well-understood pattern that the team can implement correctly.

When the team grows or the scale justifies it (≥100K notifications/second sustained), Kafka can be re-evaluated. Until then, Redis Streams is the pragmatic choice.
