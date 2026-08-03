# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications—emails and webhooks for task updates, assignments, and completions—synchronously inside the HTTP request cycle. This causes request timeouts (avg 800ms, spikes to 8s), silent failures with no retry or dead-letter queue, cascading connection-pool exhaustion from slow webhooks, and no delivery guarantees for billing-critical notifications.

We need to:
- Decouple notifications from the HTTP cycle via async processing
- Support retry with exponential backoff
- Guarantee at-least-once delivery; exactly-once for billing events
- Prepare for real-time WebSocket push notifications within 2 quarters
- Handle 10x traffic growth (~5,000 req/s peak) without re-architecting

Constraints:
- 6-person team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already in production for sessions and rate limiting
- No Kafka experience on the team
- ≤2 weeks of setup/migration before delivering value
- Modest budget; managed Confluent Cloud at full scale is not affordable
- Must maintain exactly-once semantics for billing notifications

## Decision

**Choose Redis Streams as the notification broker.**

Redis Streams (XADD / XREADGROUP / XACK / XPENDING / XAUTOCLAIM) provides consumer-group semantics, persistent-at-disk message storage, and delivery tracking sufficient for our current and projected scale—while requiring zero new infrastructure and minimal ramp-up time.

Exactly-once semantics for billing notifications will be implemented at the application layer using PostgreSQL-backed idempotency keys (a `notification_deliveries` table with a unique constraint on `notification_id + channel`). This is the standard pattern when the broker provides at-least-once and the consumer deduplicates—a pattern we control end-to-end and can reason about without distributed transaction support from the broker.

Kafka is the stronger broker in isolation, but it fails the team and timeline constraints outright: no operational experience, no dedicated infra engineer, and a setup/migration window of two weeks that must produce working value. Self-hosted Kafka introduces ZooKeeper/KRaft, broker tuning, partition planning, and monitoring that would consume the entire window before a single notification is decoupled. Redis Streams trades some theoretical ceiling for immediate, operable progress.

## Consequences

### Pros

1. **Immediate value delivery.** Redis is already running and monitored. We can begin streaming notifications within days, not weeks—adding XADD to the Flask monolith and a consumer process reading via XREADGROUP.
2. **Fits team capacity.** No new operational domain. The team already understands Redis persistence (RDB + AOF), memory management, and alerting. Kafka would require learning broker administration, partition strategy, consumer lag monitoring, and more.
3. **Scales to target.** Redis Streams handles tens of thousands of messages per second on a single instance. Our 10x target (~5,000 req/s peak, of which only a fraction are notification-producing) is well within that range. No sharding or clustering needed at projected scale.
4. **Consumer groups built-in.** XREADGROUP provides named consumer groups with delivery tracking (XPENDING for unacknowledged messages, XAUTOCLAIM for claim-after-timeout). This gives us retry semantics and at-least-once delivery without custom coordination.
5. **Budget-neutral.** No new infrastructure cost. Redis is already a line item.
6. **Extensible to WebSocket push.** The same stream can feed a WebSocket fan-out worker in a later quarter—no broker change required.
7. **Application-level exactly-once is auditable.** Deduplication through a PostgreSQL idempotency table gives us a clear, inspectable record of what was delivered, rather than relying on opaque broker-level transaction state.

### Cons

1. **No broker-level exactly-once.** Redis Streams provides at-least-once. Exactly-once for billing notifications depends on the application-layer idempotency table. If a bug in the consumer logic skips the dedup check, duplicates reach the downstream provider. Mitigation: mandatory code review on all billing-notification consumer paths; integration tests that assert idempotency-key uniqueness.
2. **Memory-bound retention.** Redis Streams reside in memory (with optional disk persistence via AOF/RDB). Long retention at high volume increases memory pressure. We will cap stream length with MAXLEN (~100k messages, covering ~2 hours at peak) and rely on the consumer keeping up—acceptable because notifications are fire-and-consume, not event-sourced replay. If we later need longer retention for audit, we archive to PostgreSQL before trimming.
3. **Less mature consumer-group tooling.** Kafka's consumer group protocol is battle-tested across thousands of deployments; Redis Streams consumer groups are simpler and less proven at extreme scale. At our scale this is not a practical risk, but it means fewer operational runbooks and third-party tools.
4. **Future migration possible.** If we eventually exceed Redis Streams' practical limits (e.g., sustained >50k msg/s or multi-day retention requirements), we will need to migrate to Kafka or a similar system. The consumer-group abstraction we build will insulate application code from that change, but the migration itself will be non-trivial.
5. **Single-node Redis is a SPOF.** Our current Redis is not clustered. We should enable Redis Sentinel or Cluster before relying on it for notification delivery, adding some operational scope within the 2-week window. This is still far less work than standing up Kafka.

## Alternatives Considered

### Apache Kafka

Kafka provides partitioned, replicated, disk-based log storage with strong ordering guarantees per partition, idempotent producers, and transactional consumers that enable broker-level exactly-once semantics. It handles virtually unlimited throughput and retention, and its consumer group protocol is industry-standard.

**Why rejected:**

| Factor | Kafka | Our requirement |
|---|---|---|
| Operational complexity | High—brokers, controllers (KRaft), partition management, rebalancing, lag monitoring | No dedicated infra engineer; 6-person team |
| Team experience | None | Must deliver in ≤2 weeks |
| Setup time (self-hosted) | 1–2 weeks minimum for a production-grade cluster with monitoring, before any application work | Entire migration window is 2 weeks total |
| Cost (managed) | Confluent Cloud: expensive at our projected scale; budget is modest | Budget-constrained |
| Exactly-once | Native via transactions | Valuable, but achievable via application-level idempotency for our billing case |
| Scale ceiling needed | Kafka handles millions of msg/s | We need ~5,000 req/s peak (10x current); only a fraction produce notifications |

Kafka's strengths—massive scale, long retention, broker-level exactly-once—are overbuilt for our current and near-term needs, while its operational demands are underbuilt for our team. Revisiting Kafka if we hit Redis Streams' practical limits is a viable future path; starting with it now is not.

### Redis Pub/Sub (not Streams)

Redis Pub/Sub is fire-and-forget: offline consumers miss messages, there are no consumer groups, no persistence, no replay, and no delivery tracking. It fails every reliability requirement (retry, at-least-once, exactly-once) and was not seriously considered.

### RabbitMQ / AWS SQS

A message queue (rather than a log) would satisfy async delivery but lacks the consumer-group replay semantics useful for WebSocket fan-out and backfill scenarios. It also introduces a new infrastructure dependency. Redis Streams gives us log-style semantics with no new infrastructure.