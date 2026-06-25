# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

### The Problem

The notification module (email + webhooks on task events) runs synchronously inside the Flask HTTP request cycle. This has caused:

- **Request timeouts**: Average notification latency is 800 ms; spikes reach 8 s during peak hours, directly inflating p95/p99 API response times.
- **Silent drops**: Provider timeouts or endpoint failures result in zero retry — billing-critical events ("trial expired", "payment failed") are lost.
- **Cascading failures**: Two production incidents where a slow webhook endpoint exhausted the shared connection pool, degrading unrelated features.
- **No delivery guarantees**: Exactly-once semantics are required for billing events but do not exist today.

### Constraints Driving the Decision

| Constraint | Implication |
|---|---|
| 6-person team, no dedicated infra engineer | Operational complexity must be low; no time for deep Kafka expertise development |
| Redis already in production (sessions, rate-limiting) | Marginal cost to extend Redis is near zero |
| No Kafka experience on the team | Kafka's operational overhead is a real risk at this team size |
| 2-week max migration window | Must deliver value quickly, not perfect a complex setup |
| Modest budget, no Confluent Cloud | Self-managed Kafka on EC2 adds significant ops burden |
| Exactly-once semantics required for billing events | Must be a first-class guarantee, not bolted on |
| 10× traffic growth target | Architecture must scale without re-architecting |
| WebSocket push notifications planned within 2 quarters | Broker must coexist with a separate real-time push layer |

### Scale Baseline

- ~2 M tasks/month → ~800 events/minute average
- Peak: 500 req/s → estimated ~50–150 notification events/s at peak
- 10× growth target: ~1,500 events/s sustained
- Message size: small (JSON payload, <10 KB typical)

---

## Decision

**Chosen: Redis Streams**

Redis Streams is adopted as the notification broker. A lightweight Python worker process consumes from stream consumer groups and dispatches to email providers (SMTP/SaaS API) and webhook endpoints, with per-event-type retry using exponential backoff and a dead-letter stream for manual inspection.

### Justification

#### 1. Operational Familiarity

Redis is already in production. The team already knows Redis-cli, persistence semantics, and failure modes. Adding Redis Streams means **zero new infrastructure, zero new operational knowledge**, and **no new servers to provision**. This directly satisfies the 2-week migration constraint.

Kafka, by contrast, requires learning broker configuration, topic partitioning strategies, consumer group offset management, schema registry (for meaningful exactly-once), replication factor tuning, and cluster sizing. For a 6-person team with no dedicated infra engineer, this is a multi-month investment before the system is trustworthy in production.

#### 2. Exactly-Once Delivery

Redis Streams supports **consumer group blocking reads with manual acknowledgment** (`XREADGROUP` + `XACK`). Combined with **idempotent notification handlers** (deduplication via a Redis SET keyed on `event_id`), the system achieves exactly-once semantics for billing events within the application's control layer. The broker itself provides at-least-once; the application layer provides deduplication.

Kafka provides exactly-once semantics natively via **transactions** and **EOS (exactly-once semantics)** configuration. However, this comes with significant complexity:
- You need a schema registry to ensure producer/consumer schema compatibility.
- You need to carefully manage transactional producers to avoid duplicates on retry.
- End-to-end exactly-once across Kafka → external systems (webhooks, email APIs) still requires idempotency logic in the consumer; Kafka's exactly-once does not extend beyond the broker boundary.

For this team's context, **application-level idempotency on top of at-least-once Streams** is equivalent in practice to exactly-once for billing events, with far less operational risk.

#### 3. Throughput and Scaling

| Metric | Redis Streams | Apache Kafka |
|---|---|---|
| Sustained throughput | ~50,000–100,000 msg/s on a single instance (per Redis docs) | ~100,000–1,000,000 msg/s per broker (partitioned) |
| Required for this system | ~1,500 events/s peak (10× growth) | Far exceeds requirements |
| Scales to 10× | Easily handles 1,500 msg/s | Overkill; adds complexity |

Redis Streams easily handles the 1,500 events/s peak target — a single consumer group can process this on modest hardware. Kafka's throughput advantage is irrelevant at this scale.

If throughput becomes a bottleneck in the future, Redis Streams can be replaced with Kafka with no change to the producer side (the Flask app just writes to a different endpoint). The producer is already decoupled.

#### 4. Message Retention

Redis Streams retains messages for the **configured `MAXLEN`** or until explicitly trimmed. With a modest `MAXLEN` of ~100,000 and a consumer that processes within seconds/minutes, retention is sufficient for retry windows and debugging.

Kafka's configurable retention (hours, days, weeks) is more powerful but also more complex to manage. For notification workloads with short processing windows, Redis Streams' retention model is simpler and fit-for-purpose.

#### 5. Consumer Groups

Both Redis Streams and Kafka support consumer groups for **competing consumers** (multiple workers processing the same stream in parallel). Redis Streams' `XREADGROUP` with `BLOCK` provides equivalent parallelism to Kafka's partition-based consumers, with simpler rebalancing via the `GROUPS` admin interface.

#### 6. Operational Complexity

| Concern | Redis Streams | Kafka |
|---|---|---|
| Infrastructure | Already exists | New cluster (3+ brokers for HA) |
| Monitoring | Existing Redis stack | New metrics (consumer lag, broker health, topic throughput) |
| Failure recovery | Single Redis instance failover | Replica brokers, ISR tuning, unclean leader election |
| Team expertise | Already available | Requires training or consulting |
| Setup time | < 1 week | 2–4 weeks for production-ready cluster |

The 2-week migration constraint is achievable with Redis Streams. It is not realistically achievable with a production-grade Kafka deployment given no prior experience.

#### 7. Cost

Redis Streams requires no additional infrastructure (Redis is already running). Self-managed Kafka on EC2 requires a minimum of 3 brokers for HA (at ~$50–100/month each), plus monitoring, backups, and schema registry infrastructure. At this team's budget, Kafka's operational cost is significant even before considering Confluent Cloud.

---

## Consequences

### Pros of Redis Streams

1. **Zero new infrastructure**: Uses existing Redis instance; no new servers, no new cloud resources.
2. **Team familiarity**: Existing Redis knowledge transfers directly; no ramp-up time.
3. **Rapid delivery**: A working producer → Streams → worker pipeline can be built in days, not weeks.
4. **Sufficient throughput**: Handles 1,500 events/s (10× growth target) comfortably on existing hardware.
5. **At-least-once + idempotency = exactly-once**: Billing events deduplicated via `event_id` SET in Redis; achieves the hard requirement.
6. **Simpler failure model**: Single Redis instance failure is well-understood; the team can reason about it.
7. **Integration with existing rate-limiting Redis**: Notifications can share the Redis connection pool, minimizing resource use.
8. **WebSocket compatibility**: Redis pub/sub can coexist with Streams for the planned WebSocket push layer — they share the same Redis instance and can reuse the same notification event model.

### Cons of Redis Streams

1. **Not a purpose-built event streaming platform**: Lacks Kafka's rich ecosystem (Kafka Connect, Kafka Streams, schema registry). If the notification system evolves into a full event-sourcing architecture, Redis Streams will be a bottleneck.
2. **Persistence coupling**: Redis persistence (RDB/AOF) affects Streams reliability. Misconfigured persistence can lead to message loss on restart. This requires Redis configuration review but is manageable.
3. **No native replay from offset**: Unlike Kafka, Redis Streams' consumer groups track pending entries (via `XPENDING`), but replaying from an arbitrary historical offset is less flexible. For retry and replay within a bounded window, this is not a practical limitation.
4. **Scaling beyond one Redis instance**: Redis Streams is primarily single-master. Horizontal scaling requires Redis Cluster, which is more complex and has different tradeoffs than Kafka's partitioned model. At the 10× growth target (1,500 msg/s), vertical scaling of a single Redis instance is still adequate.
5. **No native dead-letter queue**: Must be implemented manually (e.g., a separate stream `notifications.dlq` for failed messages after max retries). Kafka has native DLQ support via `__consumer_offsets` and dead-letter topics.
6. **Operational ceiling**: If the team grows or the system scales beyond ~50,000 events/s, Redis Streams' operational model becomes limiting. Migration to Kafka at that point would require a producer-side change only (Streams can be the source, Kafka the new sink).

---

## Alternatives Considered

### Apache Kafka

Kafka was evaluated and rejected for the following reasons:

1. **No team experience**: Zero prior Kafka knowledge means a steep learning curve during the migration. The 2-week constraint would be violated or the team would deploy a poorly configured cluster.
2. **Excessive throughput for current scale**: Kafka's 100,000+ msg/s per broker capacity is 2 orders of magnitude above the 1,500 msg/s peak target. The complexity premium is not justified at this scale.
3. **Operational overhead**: Broker health, ISR replication, unclean leader election, ZooKeeper (or KRaft) mode, schema registry, consumer group lag monitoring — all of this requires dedicated infrastructure engineering attention that a 6-person product team cannot spare.
4. **Higher cost**: Minimum 3-broker HA cluster on EC2 costs $150–300/month minimum, plus monitoring and maintenance labor.
5. **Kafka is overkill for notification dispatch**: This is a notification system, not an event-sourcing platform. The richness of Kafka's event-streaming model (log compaction, Kafka Streams, Connect) is not needed.

Kafka would be the correct choice if:
- The team had dedicated infrastructure engineers.
- The system required event replay across weeks or months.
- The throughput target exceeded ~50,000 events/s.
- The architecture was evolving toward event sourcing with multiple downstream consumers per event type.
- There was budget for Confluent Cloud managed Kafka.

**Kafka is rejected based on team constraints and scale mismatch, not technical capability.**

---

## Summary Table

| Criterion | Redis Streams | Apache Kafka |
|---|---|---|
| Operational familiarity | ✅ Existing team knowledge | ❌ No experience |
| Infrastructure needed | ✅ None (Redis exists) | ❌ 3+ new servers |
| Migration time | ✅ < 2 weeks | ❌ 2–4+ weeks |
| Throughput (current: ~150/s, target: 1,500/s) | ✅ More than sufficient | ✅ Far exceeds |
| Exactly-once for billing | ✅ Via XACK + idempotency | ✅ Native EOS (complex) |
| Consumer groups | ✅ XREADGROUP | ✅ Partition-based |
| Message retention | ✅ Configurable MAXLEN | ✅ Weeks/months configurable |
| Dead-letter queue | ⚠️ Manual (extra stream) | ✅ Native |
| Scaling beyond 50k msg/s | ⚠️ Requires Cluster | ✅ Native partitioning |
| Cost | ✅ Marginal | ❌ $150–300+/month |
| WebSocket integration | ✅ Share Redis instance | ❌ Separate system |
