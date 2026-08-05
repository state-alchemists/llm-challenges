# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

### The Problem

Our SaaS project management platform handles ~2M task events per month with a peak of ~500 req/s. Notifications (email, webhooks) are currently sent **synchronously inside the HTTP request cycle**, causing:

1. **Request timeouts** — average 800 ms latency, spikes to 8 s at peak. This directly degrades user-facing SLA.
2. **Silent failures** — a down email provider or webhook endpoint drops notifications with no retry and no dead-letter queue.
3. **Cascading failures** — two production incidents where a slow webhook endpoint exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") require exactly-once delivery; the current system provides none.

### Scaling Target

- Decouple notifications from the HTTP request cycle (async processing)
- Retry with exponential backoff
- At-least-once delivery for all events; exactly-once for billing events
- Real-time WebSocket push notifications within 2 quarters
- Handle 10× traffic growth (~5,000 req/s) without re-architecting

### Team Constraints

| Constraint | Detail |
|---|---|
| Team size | 6 engineers (3 senior, 3 mid-level), **no dedicated infrastructure engineer** |
| Kafka experience | Zero on the team today |
| Existing Redis | Already in production for sessions and rate limiting |
| Setup timeline | Must deliver value within **2 weeks** |
| Budget | Modest — cannot afford Confluent Cloud managed Kafka at scale |
| Exactly-once requirement | **Mandatory** for billing notifications |

---

## Decision

**Chosen: Redis Streams**

Redis Streams is the correct choice given our team size, operational constraints, existing Redis footprint, and timeline. The decision is driven by:

1. **Operational familiarity** — Redis is already running in production. The team will not face the learning curve, deployment complexity, or operational burden of a Kafka cluster ( ZooKeeper/KRaft, partition leadership, replication factor tuning, broker monitoring).
2. **Timeline** — Kafka requires a minimum of 2–4 weeks to deploy, configure, and for the team to become productive. Redis Streams can be integrated in days; the team writes Python/Flask and already uses `redis-py`.
3. **Infrastructure cost** — Self-managed Kafka on 4 web servers adds significant operational complexity. Confluent Cloud or MSK costs money we do not have budgeted today. Redis Streams shares the existing Redis instance.
4. **Throughput adequacy** — At peak 500 req/s (5,000 req/s in 2 years), Redis Streams handles 50,000–100,000 events/second per node. We are not at Kafka-scale problems.
5. **Ordering and consumer groups** — Redis Streams provides per-stream FIFO ordering and consumer group semantics (`XREADGROUP`, `XACK`) that cover our retry and acknowledgment requirements.

The exactly-once guarantee for billing events is achieved by using a **deduplication table in PostgreSQL** (idempotency key per notification) combined with `XACK` semantics — standard practice and explicitly supported by Redis Streams documentation.

---

## Consequences

### Pros of Redis Streams

| Property | Detail |
|---|---|
| **Operational simplicity** | Shares the existing Redis instance. No new system to deploy, monitor, or operate beyond configuration changes. |
| **Fast integration** | `redis-py` already in use. `XADD`, `XREADGROUP`, `XACK`, `XRANGE` are the core primitives; a mid-level engineer can be productive in hours. |
| **Throughput** | 50,000–100,000 events/second per Redis node. Current peak is 500 req/s; 10× growth is 5,000 req/s — well within Redis Streams' capacity. |
| **Ordering guarantees** | Per-stream FIFO ordering. All notifications for a given task or user can be routed to the same stream key for ordering. |
| **Consumer groups** | `XREADGROUP` provides at-least-once delivery with manual acknowledgment (`XACK`). Failed deliveries are automatically retried by pending message re-reading. |
| **Message retention** | Configurable via `MAXLEN` or `MINID` trimming. Supports `XPENDING` for monitoring stuck deliveries. |
| **Existing infra investment** | Redis is already provisioned, monitored, and battle-tested in this stack. |
| **WebSocket roadmap** | Redis Pub/Sub can serve as the real-time push channel for WebSocket notifications in a future quarter, using the same Redis instance. |

### Cons of Redis Streams

| Property | Risk | Mitigation |
|---|---|---|
| **No native exactly-once** | Redis Streams guarantees at-least-once, not exactly-once. A consumer crash after `XADD` but before `XACK` can cause duplicate delivery. | PostgreSQL deduplication table keyed on idempotency ID. On consume, check and insert before sending; skip if already processed. |
| **Persistence dependency** | If the Redis instance goes down, notifications are unavailable. | Enable AOF persistence with `appendfsync everysec` (good balance of speed and durability). Consider Redis replication to a read replica for HA. |
| **Stream size management** | Unbounded streams grow until trimmed. Misconfigured `MAXLEN` can drop messages under load. | Set `MAXLEN ~` (approximate trimming) at `XADD` time. Monitor stream length via `XDBSIZE`. |
| **No native dead-letter queue** | A poison-pill message that always fails will loop forever. | Implement a max-delivery-count check: after N `XACK` failures, move to a dead-letter sorted set or a dedicated `notifications.dlq` stream. |
| **Single-node throughput ceiling** | A single Redis node caps at ~100K events/sec. For 10× growth (5,000 req/s) this is fine; beyond 50× it would be a constraint. | Redis Cluster mode can shard streams if needed. Addressed at that scale, not today. |
| **Fan-out complexity** | Delivering the same notification to multiple consumers (e.g., email + webhook + WebSocket) requires multiple `XADD` calls or a fan-out pattern. | Publish once to a `notifications.all` stream; let each consumer group handle its own delivery type. |

---

## Alternatives Considered

### Apache Kafka

| Property | Kafka | Redis Streams | Verdict |
|---|---|---|---|
| **Throughput** | 100,000–1,000,000 events/sec | 50,000–100,000 events/sec | Redis Streams adequate at current + 10× scale |
| **Exactly-once semantics** | Native via Kafka Transactions (idempotent producer + transactional consumer) | At-least-once + deduplication table | Kafka wins natively, but the dedup table is a known pattern that solves this |
| **Ordering guarantees** | Per-partition | Per-stream | Equivalent for our use case |
| **Consumer groups** | Mature, rich ecosystem (Kafka Streams, Flink connectors) | Basic but sufficient (`XREADGROUP`, `XACK`) | Kafka wins for complex streaming ecosystems; overkill here |
| **Operational complexity** | **High** — ZooKeeper/KRaft, broker config, partition leadership, replication tuning, log retention, consumer group offset management | **Low** — Redis already running; no new daemons | Redis Streams |
| **Setup time** | 2–4 weeks minimum to deploy and for team to become productive | 2–5 days | Redis Streams |
| **Infrastructure cost** | Self-managed on EC2 (complex) or Confluent Cloud / MSK (expensive). At 5,000 req/s, Confluent Cloud starts at ~$400/month. | Shares existing Redis (~$30–80/month for a suitable instance). | Redis Streams |
| **Team experience** | Zero Kafka experience | Existing Redis proficiency | Redis Streams |
| **Message retention** | Days to weeks; log-compacted topics for indefinite retention | Bounded by `MAXLEN` or `MINID`; unbounded only with memory | Kafka wins for audit-log retention use cases; not our requirement |

**Why Kafka was rejected:**

Kafka is the industry standard for high-throughput event streaming and is the correct choice for teams with dedicated platform/infrastructure engineers, traffic above ~50,000 events/second, or a need for the rich Kafka ecosystem (Kafka Streams, Connect, Flink). None of those conditions apply here:

- We have no Kafka expertise and no infrastructure engineer to own it.
- Our current and projected throughput (500–5,000 req/s) is within Redis Streams' comfortable range.
- The 2-week constraint makes Kafka's ramp-up time prohibitive.
- Budget cannot absorb Confluent Cloud or MSK costs.

Kafka would be the right answer if this system were to grow into a multi-team, high-throughput event platform. At our current scale and constraints, it adds operational risk and timeline risk that the team cannot absorb.

---

## Summary

| Requirement | Redis Streams | Kafka |
|---|---|---|
| Async decoupling from HTTP | ✅ | ✅ |
| Retry with exponential backoff | ✅ (via pending + `XCLAIM`) | ✅ |
| At-least-once delivery | ✅ (`XREADGROUP` + `XACK`) | ✅ |
| Exactly-once for billing | ✅ (dedup table) | ✅ (native) |
| 10× throughput headroom | ✅ | ✅ |
| Operational within 2 weeks | ✅ | ❌ |
| No new infra systems | ✅ | ❌ |
| Team already knows it | ✅ | ❌ |
