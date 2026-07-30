# ADR-001: Notification Subsystem Messaging Platform

## Status

Proposed

---

## Context

Our Flask monolith handles notifications synchronously inside the HTTP request cycle, causing:

- **Latency**: Average notification latency of 800 ms, spiking to 8 s under load, directly blocking API responses.
- **Reliability**: Silent drops on provider failure; no retry, no dead-letter queue.
- **Cascading failures**: Slow webhook endpoints have twice exhausted the connection pool, taking down unrelated features.
- **Missing guarantees**: Billing-critical notifications (trial expiry, payment failure) lack delivery guarantees.

Scaling targets require async processing with at-least-once delivery (billing events), retry with exponential backoff, and a path to WebSocket push notifications. The system must handle 10x traffic growth.

**Constraints:**
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already runs in production for session storage and rate limiting.
- Zero Kafka experience on the team.
- Migration must deliver value within 2 weeks.
- Modest budget; Confluent Cloud at full scale is unaffordable.
- Billing notifications require exactly-once semantics.

---

## Decision

**Choose Redis Streams.**

Redis Streams provides the right balance of reliability, operational simplicity, and team-fit for this workload. At a peak of ~500 req/s (~2 M events/month), Redis Streams comfortably handles the throughput (500 k–1 M msg/s on commodity hardware) while sharing the existing Redis infrastructure, eliminating new operational burden.

---

## Consequences

### Pros

| Property | Redis Streams |
|---|---|
| **Operational footprint** | Zero new infrastructure — runs on the Redis cluster already in production. |
| **Time to value** | Days, not weeks. No cluster to provision, no broker configuration to learn. |
| **Throughput** | 500 k–1 M msg/s on a single Redis instance — 1000× headroom over current peak. |
| **Ordering** | FIFO within a consumer group, which is sufficient for notification ordering per user. |
| **At-least-once delivery** | `XREADGROUP` + `XACK` provides durable at-least-once delivery out of the box. |
| **Consumer groups** | Native `XGROUP` / `XREADGROUP` / `XACK` with per-group position tracking and redelivery on failure. |
| **Message retention** | Configurable by stream or by time-to-live (`MAXLEN` or `MINID`), up to indefinitely on a stream with `MAXLEN 0`. |
| **Retry logic** | Consumer-side implementation with exponential backoff and a dead-letter stream (`XADD dlq ...`). |
| **Scaling path** | Redis Cluster mode can shard streams horizontally; vertical scaling is sufficient for 10× growth on a single instance. |
| **WebSocket readiness** | A worker process can publish to a Redis channel that a WebSocket server subscribes to for real-time push. |
| **Team familiarity** | The team already operates and monitors Redis; no net new operational knowledge required. |

### Cons

| Issue | Detail |
|---|---|
| **Exactly-once requires work** | Redis Streams guarantees at-least-once (via `XACK`). Exactly-once delivery for billing events requires an idempotency layer on the consumer side (e.g., deduplication keys stored in Redis with `SETNX` and a TTL). This is a well-understood pattern but adds implementation work — estimated 1–2 days. |
| **No native partitioning** | Unlike Kafka's topic-partition model, horizontal scaling of consumption rate requires multiple consumer groups or sharding streams by user ID. At current scale this is not a concern; at 10× it is addressable with Redis Cluster sharding. |
| **Message accumulation risk** | If a consumer group falls behind, stream length grows unbounded unless `MAXLEN` is enforced. Must configure appropriate truncation policies. |
| **Operational limits at extreme scale** | At 100×+ current scale, Redis Streams would require significant re-architecture (Redis Cluster, careful key distribution). The 10× target is safely within single-instance capacity. |
| **No native pluggable connectors** | Kafka's rich connector ecosystem (JDBC sinks, etc.) does not exist for Redis Streams. Any new sink requires a custom consumer. |

---

## Alternatives Considered

### Apache Kafka

Kafka offers best-in-class guarantees and ecosystem but carries significant costs for this team and scale.

| Property | Kafka | Redis Streams |
|---|---|---|
| **Exactly-once semantics** | Native EOS with Kafka Transactions (idempotent producer + consumer offset commit atomically) | Consumer-side idempotency (dedup keys) |
| **Throughput** | Millions of msg/s | 500 k–1 M msg/s |
| **Operational complexity** | Requires ZooKeeper or KRaft mode, partition management, replication factor, log retention tuning, consumer group rebalancing, JVM tuning | Runs on existing Redis; no new service |
| **Learning curve** | No team experience; 2-week deadline at risk | Familiar to team |
| **Managed option cost** | Confluent Cloud at relevant scale: $1 k–$5 k+/month | Redis Cloud or ElastiCache: already paying for Redis |
| **Message retention** | Per-topic, configurable to days/weeks, zero data loss on replay | Per-stream, configurable; but long retention on a single Redis instance has memory implications |
| **Consumer groups** | Mature, rich rebalancing strategies | Native but simpler model |

**Why rejected:** Kafka's operational complexity is the deciding factor. A 6-person team with no Kafka experience cannot safely stand up, tune, and operate a production-grade Kafka cluster within 2 weeks. Self-managed Kafka on EC2 requires choosing partition counts, replication factors, log segment sizes, JVM heap settings, and retention policies — decisions that are hard to reverse and require experience the team does not have. Managed Confluent Cloud is outside the budget envelope. The throughput and ordering guarantees Kafka offers are also far beyond what 500 req/s demands; Redis Streams provides adequate headroom at a fraction of the operational cost.

Kafka becomes the correct choice if the team grows a dedicated platform/infrastructure function, the notification system needs multi-region replication with ordered event sourcing, or the scale exceeds 50 k req/s sustained. Those conditions do not exist today.

---

## Summary

Redis Streams is the right choice for the current team size, existing infrastructure, skill set, and scale. It solves all four stated problems — async decoupling, retry with backoff, at-least-once delivery, and failure isolation — with zero new infrastructure and minimal learning curve. Exactly-once for billing events requires a thin consumer-side deduplication layer (1–2 days of work) which is a reasonable trade-off against Kafka's weeks-long onboarding and operational overhead.
