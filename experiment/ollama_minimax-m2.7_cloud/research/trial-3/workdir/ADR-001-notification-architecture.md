# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

The notification module (email + webhooks) runs synchronously inside the Flask HTTP request cycle. This causes:

1. **Request timeouts** — average 800ms, spikes to 8s at peak. Users experience degraded API responsiveness.
2. **Silent failures** — downstream email provider or webhook endpoint downtime results in zero retry; the notification is discarded.
3. **Cascading failures** — a slow webhook consumer once exhausted the shared connection pool, degrading unrelated features.
4. **No delivery guarantees** — billing-critical events (trial expiry, payment failure) have no exactly-once guarantee.

Scaling targets:
- Decouple async notification delivery from the request cycle
- Retry with exponential backoff; dead-letter handling for permanently failed messages
- At-least-once for general notifications; exactly-once for billing-critical events
- Real-time WebSocket push within 2 quarters
- 10x traffic growth without re-architecting

Constraints:
- Team: 6 engineers (3 senior, 3 mid-level), **no dedicated infrastructure engineer**
- **No Kafka experience** on the team today
- Redis is already in production (session storage, rate limiting)
- **Setup/migration must not exceed 2 weeks**
- Budget: modest — Confluent Cloud at full scale is not affordable
- Must maintain exactly-once semantics for billing notifications

### Relevant System Metrics

| Metric | Value |
|---|---|
| Monthly active users | 85,000 |
| Tasks created/month | ~2,000,000 |
| Peak request rate | ~500 req/s |
| Estimated peak notification throughput | 100–200 msg/s |
| 10x growth target throughput | 1,000–2,000 msg/s |

---

## Decision

**Use Redis Streams as the notification subsystem message broker.**

The recommendation is to implement a Redis Streams-based worker architecture, using consumer groups for reliable delivery and application-level deduplication for billing-critical exactly-once semantics.

---

## Rationale

### Why Redis Streams fits

**Operational continuity.** Redis is already running in production. The team has direct operational experience with it: monitoring, persistence configuration, failover behavior, and failure modes are understood. Introducing Kafka requires acquiring entirely new operational knowledge — broker configuration, topic partitioning, consumer group offset management, JVM tuning (if using self-managed), or significant cost and lock-in (if using Confluent Cloud). For a 6-person team with no dedicated infra engineer, this is not a marginal risk.

**Time-to-value.** Redis Streams requires no new server infrastructure, no new service discovery, and no new operational tooling. A Python worker process using `redis-py` with the Streams API can be stood up in days. The migration from inline notification calls to pushing events onto a stream is a localized code change. Kafka requires broker provisioning, topic design (partition counts, replication factors), schema registry decisions, and CI/CD pipeline changes — realistically 3–6 weeks for a team with existing Kafka experience, longer without it.

**Throughput is sufficient.** At current peak (~200 msg/s notification rate) and 10x growth (~2,000 msg/s), Redis Streams comfortably handles the load on a single instance. Published benchmarks and operational reports show effective throughput of 50,000–100,000 msg/s on commodity cloud instances for Redis Streams. Sharding (via Redis Cluster) can be added if truly needed, though the 10x target does not approach that ceiling.

**Exactly-once for billing events — achievable with application-layer deduplication.** Redis Streams alone provides at-least-once (via `XREADGROUP` + `XACK`). However, exactly-once semantics for billing notifications are achievable by using a **deduplication table in PostgreSQL** (the existing database). The notification payload for a billing event includes a stable idempotency key (e.g., `billing_event:{user_id}:{event_type}:{period}`). Before publishing or before processing, the worker checks/inserts this key in a `notification_idempotency` table with a unique constraint. If the key exists, the notification is skipped. This pattern is straightforward, requires no new infrastructure, and is the same pattern used with Kafka when exactly-once is required at the application level.

---

## Consequences

### Pros

- **Fastest path to async delivery.** A `XADD` to push a notification event is a single round-trip from the Flask handler. The handler returns immediately; the worker consumes and delivers out-of-band.
- **Operational simplicity.** One new process type (worker), one new Redis stream key pattern. No new servers, no new monitoring dashboards for a message broker — reuse existing Redis infrastructure.
- **Retry with exponential backoff.** Workers track failed deliveries in a pending entries list (`XPENDING`). Use `XCLAIM` with a `MIN-IDLE-TIME` threshold to reassign messages after backoff intervals. Dead letters can be moved to a dedicated stream (`notification.dlq`) after N retries.
- **Consumer groups.** Multiple workers can consume from the same stream with `XREADGROUP`, providing horizontal scaling and load distribution. Group state (last acknowledged message ID) is maintained by Redis.
- **Message retention.** Streams retain messages for a configurable window (e.g., 7 days) via `MAXLEN`. This provides replay capability without a separate message store.
- **WebSocket readiness.** A separate WebSocket worker can consume the same stream to push real-time events to connected clients. This aligns directly with the 2-quarter roadmap goal.
- **Cost.** Uses existing Redis infrastructure. No additional managed service cost.

### Cons

- **At-least-once only from the broker.** Without application-layer deduplication, Redis Streams does not guarantee exactly-once. The PostgreSQL deduplication table mitigates this for billing events, but it adds a database round-trip per notification.
- **No native dead-letter queue.** Failed messages after max retries must be moved manually to a DLQ stream (`XADD notification.dlq ...`). This is a small amount of custom code but is not built-in.
- **No native message routing.** Kafka's topic-based routing allows separating email, webhook, and push notification consumers by topic. With Redis Streams, this requires either separate stream keys (`notifications.email`, `notifications.webhook`) or a discriminator field inside each message that workers inspect.
- **Operational ceiling.** If the team grows to 20+ engineers and notification volume reaches 50,000+ msg/s, Redis Streams on a single instance will require careful sharding planning. Kafka would scale more naturally here. However, this ceiling is well beyond the 10x growth target.
- **Memory usage.** Messages in the stream consume RAM proportional to the retention window. At high throughput with long retention, this adds pressure. Set `MAXLEN` appropriately (e.g., 10,000–50,000 per stream) or use `MAXLEN ~` trimming to keep only the working set.

---

## Alternatives Considered

### Apache Kafka

**Why it was considered.** Kafka is the industry standard for event streaming at scale. It provides durable, ordered, replayable message logs with strong delivery guarantees. Consumer groups, topic partitioning, and exactly-once semantics (via idempotent producers + transactions) are mature and well-documented.

**Why it was rejected for this context.**

| Factor | Kafka | Redis Streams |
|---|---|---|
| Team experience | Zero | Familiar |
| Setup time | 3–6 weeks (realistic, even with experience) | 3–5 days |
| New infrastructure | Broker cluster + Zookeeper/KRaft (or managed service cost) | None |
| Exactly-once | Native via idempotent producer + transactions | Application-layer (via PostgreSQL dedup) |
| Operational overhead | High: broker tuning, partition rebalancing, schema registry | Low: Redis already monitored |
| 10x growth fit | Overkill, but capable | Fully sufficient |
| Cost | Broker servers or Confluent Cloud subscription | Zero incremental |

Kafka's strengths are undeniable at high scale or when multiple independent consumers need to re-read the same event log independently. However, the constraints here — no infra engineer, 2-week deadline, existing Redis investment, and moderate throughput — make Kafka an excessive operational burden. The team would spend the first month learning Kafka instead of delivering the async notification decoupling that unblocks the product.

If the team grows significantly or the notification system evolves into a full event-sourcing architecture with many downstream consumers re-reading historical events, Kafka would be the correct long-term choice. At that point, a migration from Redis Streams to Kafka would be straightforward: the stream data model maps directly to a Kafka topic.

---

## Summary

| Criteria | Redis Streams | Apache Kafka |
|---|---|---|
| Fits team size/experience | ✅ Yes | ❌ No |
| 2-week delivery | ✅ Yes | ❌ No |
| Uses existing infra | ✅ Yes (Redis) | ❌ No |
| Throughput for 10x target | ✅ Sufficient | ✅ Overkill |
| Exactly-once (billing) | ✅ Via app dedup | ✅ Native |
| Retry/DLQ support | ✅ Via XPENDING + DLQ stream | ✅ Native |
| WebSocket push readiness | ✅ Yes | ✅ Yes |
| Long-term scalability ceiling | Moderate (sharding needed at very high scale) | High |

**Recommendation: Redis Streams.** Implement a notification worker that consumes from `XREADGROUP`, delivers via the appropriate channel (email provider SDK, webhook HTTP call, WebSocket push), uses `XACK` on success, and handles retries via `XPENDING`/`XCLAIM`. For billing-critical events, use a PostgreSQL idempotency-key check before delivery to guarantee exactly-once semantics. The entire implementation is achievable within two weeks with the existing team.
