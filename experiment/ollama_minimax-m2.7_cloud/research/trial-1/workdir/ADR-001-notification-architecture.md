# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

### The Problem

The notification module sends emails and webhooks synchronously inside the HTTP request cycle. This has caused:

1. **Request timeouts** — notification delivery adds 800ms average latency, spiking to 8s at peak.
2. **Silent failures** — a downed email provider or webhook endpoint drops notifications with no retry or dead-letter queue.
3. **Cascading failures** — two incidents where a slow webhook endpoint exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications (trial expired, payment failed) lack exactly-once protection.

### Scaling Target

- Decouple notifications from the HTTP request cycle (async processing)
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- WebSocket push notifications within 2 quarters
- Handle 10x traffic growth without re-architecting

### Constraints

| Constraint | Implication |
|---|---|
| Team: 6 people (3 senior, 3 mid-level), no dedicated infra engineer | Operational burden must be low; no capacity for managing complex distributed systems |
| Redis already in production (session, rate limiting) | Adding Redis Streams leverages existing infrastructure and expertise |
| No Kafka experience on the team | Kafka introduces a steep learning curve with no prior institutional knowledge |
| 2-week max setup/migration before delivering value | Technology must be straightforward to deploy and migrate |
| Modest budget | Cannot afford managed Confluent Cloud at full scale |
| Exactly-once semantics required for billing notifications | Non-negotiable for financial and contractual compliance |

### Scale Reference

- 85,000 monthly active users
- ~2M tasks created per month
- **Peak: ~500 events/s** requiring notification dispatch
- 10x growth target without re-architecting

---

## Decision

**Chosen option: Redis Streams**

### Justification

Redis Streams is the correct choice given the stated constraints. The team already operates Redis, can implement Redis Streams with existing knowledge, and can ship value within the 2-week window. The trade-offs around durability and throughput are acceptable at the current and projected scale.

**Why Redis Streams over Kafka:**

1. **Operational simplicity** — Redis Streams runs on infrastructure the team already understands and administers. There is no JVM-based broker, no ZooKeeper/KRaft quorum, no topic-partition calibration, and no schema registry. For a 6-person team with no dedicated infra engineer, this is decisive.

2. **Fastest time-to-value** — Self-hosted Kafka with proper operational rigor (monitoring, alerting, dead-letter handling, consumer group rebalance policies) typically requires 3–6 weeks of initial setup for a team with prior experience. Redis Streams can be integrated and migrated to in under 2 weeks.

3. **Existing Redis investment** — The team already uses Redis for sessions and rate limiting. Adding Streams reuses the same deployment, monitoring, and operational runbooks.

4. **Exactly-once for billing events is achievable** — Redis Streams supports consumer groups with `XACK` semantics. Combined with idempotent notification handlers (deduplication via a Redis SET or a DB-unique-constraint on `notification_id`), exactly-once can be implemented reliably without the operational complexity of Kafka Transactions.

5. **Scale is sufficient** — At 500 events/s peak, Redis Streams easily handles the load. Redis Streams can sustain 100K–500K events/s on commodity hardware. 10x growth (5,000 events/s) remains well within Redis Streams' practical throughput, and horizontal read replicas can shunt consumer groups if needed.

6. **WebSocket push notifications** — Redis Streams integrates naturally with Redis Pub/Sub for fan-out to WebSocket connections. A future WebSocket gateway can subscribe to Streams channels and push to connected clients without an additional message broker.

---

## Consequences

### Pros

| Benefit | Detail |
|---|---|
| **Operational continuity** | Leverages existing Redis infrastructure; no new services to deploy, monitor, or on-call for |
| **Team familiarity** | No new language, SDK, or operational model to learn |
| **Rapid migration** | Existing synchronous notification code can be migrated incrementally: enqueue one event type first, validate, expand |
| **Consumer groups** | `XREADGROUP` provides per-consumer-group offset tracking, fan-out to multiple consumers (email worker, webhook worker, WebSocket worker), and redelivery on failure |
| **Message retention** | `MAXLEN` or `MINID` trimming keeps Streams bounded; retention is configurable per stream |
| **Ordering guarantee** | Within a consumer group, Redis Streams preserves insertion order — critical for notification sequences (e.g., "task assigned" before "task completed") |
| **At-least-once delivery** | Unacknowledged messages are redelivered after consumer failure; exponential backoff implemented via `XCLAIM` with `MINIDLETIME` |
| **Exactly-once for billing** | Achieved by idempotent handlers: each notification carries a stable UUID; the handler writes `notification_id` to a Redis SET or DB unique key before dispatching; duplicates are detected and skipped |
| **Cost** | No additional infrastructure cost; uses existing Redis memory (Streams are compact — ~100 bytes/message) |
| **Fallback** | If Redis is unavailable, the application can fall back to a synchronous (degraded) mode with alerting |

### Cons

| Drawback | Detail |
|---|---|
| **Durability** | Redis Streams persistence is `AOF` (append-only file) by default. If Redis is restarted without `AOF fsync=everysec` or `fsync=always`, messages committed to the stream but not yet persisted to disk can be lost. Mitigation: configure `AOF fsync=always` for notification streams or use a Redis replication topology with a synchronous replica write. |
| **No native replay from offset** | Unlike Kafka, Redis Streams consumers must track their own offset via `XACK` and `XREADGROUP`. If a consumer crashes mid-batch, messages up to the last `XACK` are not automatically replayed — the consumer group manages this, but it requires care. |
| **Fan-out scaling** | A single stream with multiple consumer groups (email, webhook, WebSocket) works well at moderate scale, but high-throughput fan-out to many consumer groups creates read amplification. Mitigation: separate streams per notification category at scale. |
| **No native dead-letter queue** | Failed messages after max retries must be routed manually (e.g., `XADD notifications.dlq`). Kafka's native DLQ support is more mature. |
| **Throughput ceiling** | Sufficient for 10x current load, but Redis Streams on a single primary could become a bottleneck above ~50K events/s. Mitigation: Redis Cluster mode supports stream sharding, but adds operational complexity. |
| **Operational risk if Redis is the primary DB** | If the notification stream and the primary Redis instance share resources, high notification volume could contend with session/rate-limiting workloads. Mitigation: dedicate a Redis instance or use separate databases within the same Redis process. |

---

## Alternatives Considered

### Apache Kafka

Kafka was evaluated as the established industry standard for event streaming and would be the correct choice under different constraints.

**Strengths that made Kafka a contender:**
- **Throughput**: 100K–1M+ events/s per broker, far exceeding the current 500 events/s requirement
- **Durability**: Segmented disk writes with configurable `min.insync.replicas` provide strong durability guarantees
- **Exactly-once semantics (EOS)**: Kafka Transactions provide true exactly-once between producers and consumers without application-level deduplication
- **Native DLQ**: Dead-letter topics are a first-class pattern in Kafka
- **Time-indexed replay**: Consumers can replay from any offset or timestamp
- **Mature ecosystem**: Schema Registry, Kafka Connect, ksqlDB, and a large talent pool

**Why Kafka was rejected given the current constraints:**

| Reason | Explanation |
|---|---|
| **No team experience** | Kafka has a significant operational learning curve. A team with no prior Kafka experience will spend weeks on broker configuration, consumer group rebalance strategies, topic partitioning, and JVM tuning before shipping value. |
| **Infrastructure overhead** | Kafka requires ZooKeeper (or KRaft in newer versions), at minimum 3 brokers for HA, and separate ZooKeeper nodes. This is non-trivial to operate for a 6-person team without an infrastructure engineer. |
| **Setup time exceeds constraint** | With no prior experience, a safe Kafka deployment — including monitoring, alerting, DLQ handling, and consumer group management — realistically requires 4–8 weeks. The project constraint is 2 weeks. |
| **Budget** | Managed Kafka (Confluent Cloud, AWS MSK) at the throughput and retention needed for a notification system with billing-critical events runs $500–$2,000/month. Self-hosted Kafka on EC2 requires significantDevOps investment. |
| **Over-engineering** | Kafka's feature set — time-indexed log retention, exactly-once EOS, schema registry — exceeds what a notification subsystem with 500 events/s requires. Redis Streams delivers sufficient guarantees at a fraction of the operational cost. |
| **WebSocket integration** | Kafka does not natively speak WebSocket. A separate WebSocket gateway service and a mechanism to bridge Kafka events to WebSocket connections must be built from scratch, adding complexity. Redis Pub/Sub provides this natively. |

**Summary**: Kafka is the right tool for a high-throughput, multi-team, event-sourcing-heavy organization. For a 6-person team with a 2-week deadline, modest budget, and a notification subsystem at 500 events/s, Kafka's complexity-to-value ratio is unfavorable.

---

## Recommendation

**Implement Redis Streams for the notification subsystem.**

Start with a single `notifications` stream, two consumer groups (`email-worker`, `webhook-worker`), and idempotent handlers for billing events. Migrate synchronous notification calls incrementally: wrap the existing code in a `XADD` call and return immediately, then build workers to consume from `XREADGROUP`. Configure `AOF fsync=always` for the Redis instance handling notifications, or use a dedicated read replica to isolate the notification workload.

When (and only when) throughput exceeds ~50K events/s, a team member leaves, or the architecture demands event sourcing for other domains, revisit Kafka. Until then, Redis Streams is the pragmatic, low-risk choice that delivers value within the deadline.
