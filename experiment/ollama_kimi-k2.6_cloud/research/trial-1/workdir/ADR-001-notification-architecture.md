# ADR-001: Notification Architecture — Async Event Streaming

## Status

Proposed

## Context

Our SaaS project-management platform (85k MAU, ~500 req/s peak) currently sends email and webhook notifications synchronously inside the Flask HTTP request cycle. This causes:

- **Request timeouts**: Average notification latency 800ms, spikes to 8s during peaks.
- **Silent failures**: No retry or dead-letter queue when providers are down.
- **Cascading failures**: Slow webhook endpoints have caused connection-pool exhaustion and outages twice this year.
- **No delivery guarantees**: Billing-critical events (trial expired, payment failed) are not guaranteed exactly once.

We need to decouple notifications from HTTP requests, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), and support 10× traffic growth without re-architecting. We also plan to add real-time WebSocket push notifications within two quarters.

**Team constraints**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer. We already run Redis for sessions and rate limiting. No one on the team has operated Kafka. Budget is modest; managed Confluent Cloud is not affordable at scale today. We must deliver value within two weeks.

## Decision

We will use **Redis Streams** as the event backbone for the notification subsystem.

Redis Streams is the only option that lets us meet the two-week delivery window with our current team and skills. It provides sufficient throughput for our present scale and near-term growth, supports consumer groups for parallel processing, and lets us leverage our existing Redis operational knowledge. Its weaknesses—exactly-once semantics and retention management—are mitigated by application-level idempotency keys and explicit persistence policies.

### Technical Justification

| Property | Redis Streams | Apache Kafka |
|----------|--------------|--------------|
| **Throughput** | ~100k–500k msgs/s per node (more than adequate for 500 req/s peak and 10× growth) | Millions of msgs/s per cluster; overkill for our current scale. |
| **Ordering guarantees** | Per-stream ordering (messages appended sequentially; consumers read in insertion order). | Strong per-partition ordering; superior for complex partitioning strategies. |
| **Message retention** | Memory-bounded by `MAXLEN` or time-based trimming. Requires explicit policy tuning to avoid OOM. | Log-based, disk-persistent retention with configurable TTL/size policies. Superior for long-term replay. |
| **Consumer groups** | Built-in (Redis 5.0+). Supports auto-claim and pending-message inspection. | Mature, battle-tested consumer groups with advanced rebalancing protocols. |
| **Exactly-once semantics** | At-least-once by default. Exactly-once requires application-level idempotency (deduplication keys in Redis or PostgreSQL). | Idempotent producers + transactions provide native exactly-once semantics (EOS). |
| **Operational complexity** | **Low**: We already run Redis. Adding Streams is a config change, not a new runtime. | **High**: Requires ZooKeeper or KRaft metadata quorum, partition sizing, replication tuning, and deep operational expertise. |

Given our constraints, the operational burden of self-hosted Kafka outweighs its technical advantages. A team with no Kafka experience cannot safely deploy and operate a production Kafka cluster—including partitioning strategy, replication factor, monitoring, and failure recovery—in under two weeks. Redis Streams lets us ship immediately, iterate, and revisit Kafka when we have dedicated infrastructure capacity or budget for a managed offering.

## Consequences

### Pros

- **Fast time to value**: Can prototype in days using our existing Redis deployment; no new infrastructure to provision, secure, or monitor.
- **Low operational risk**: Team already knows Redis backup, failover, and tuning. No unknown failure modes from a new distributed system.
- **Sufficient headroom**: At 500 req/s peak with 10× growth target (5k req/s), Redis Streams is well within comfortable limits.
- **WebSocket synergy**: Redis Pub/Sub (already available) can power the planned real-time WebSocket layer, keeping the messaging stack unified.
- **Cost**: No additional license or managed-service fees.

### Cons

- **Exactly-once is application-managed**: Billing notifications require idempotency keys stored in Redis/PostgreSQL. If the deduplication layer fails, duplicates are possible. This adds code complexity.
- **Retention is memory-bound**: Long backlogs or consumer lag can exhaust RAM. We must set explicit `MAXLEN` or `MAXID` policies and monitor memory closely.
- **Less ecosystem maturity**: Fewer stream-processing libraries and observability tools compared to Kafka. We will write more custom consumer logic.
- **Harder partitioning story**: Scaling beyond a single Redis node for streams requires client-side sharding or migrating to a clustered Redis setup, which is nontrivial.
- **Possible noisy-neighbor effect**: Running Streams on the same Redis instance used for sessions and rate limiting introduces resource contention. We should isolate notification streams to a separate Redis instance or at least a separate logical database before going to production.

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the superior streaming platform on a pure technical basis: native exactly-once semantics, disk-based retention, superior consumer-group rebalancing, and a mature ecosystem of connectors and stream-processing libraries. For a company with dedicated infrastructure engineers and a longer runway, Kafka is the right default.

However, for our team, Kafka was rejected because:

1. **Team inexperience**: No engineer has operated Kafka in production. The learning curve for KRaft/ZooKeeper, partition rebalancing, and failure recovery is steep.
2. **Operational burden**: Self-hosted Kafka requires ongoing care (broker monitoring, disk management, replication lag alerting) that a 6-person product-engineering team cannot sustainably absorb without an SRE.
3. **Timeline mismatch**: A safe production deployment—including replication, monitoring, and runbooks—would take more than two weeks for this team.
4. **Budget**: Managed Kafka (Confluent Cloud, Amazon MSK) is ruled out by the modest budget constraint.

We will re-evaluate Kafka when we have either (a) a dedicated infrastructure hire, or (b) budget for a managed service and traffic levels that justify the cost.
