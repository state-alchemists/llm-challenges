# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails and webhooks for task updates, assignments, and completions — synchronously inside the HTTP request cycle. This has caused request timeouts (average latency 800ms, spikes to 8s), silent delivery failures with no retry or dead-letter queue, two cascading-failure incidents from slow webhook endpoints exhausting the connection pool, and zero delivery guarantees for billing-critical notifications ("trial expired", "payment failed").

We need to decouple notification delivery from the request cycle with an async message broker that provides:

1. **Retry with exponential backoff** for transient failures.
2. **At-least-once delivery** for all notifications; exactly-once semantics for billing events where feasible.
3. **Consumer groups** so multiple workers can process notifications in parallel.
4. **Ordered delivery** within a logical channel (e.g., per user or per project) so users see notifications in causal order.
5. **Headroom for 10x traffic growth** without re-architecting.
6. **Foundation for real-time WebSocket push** planned within two quarters.

Hard constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level). No dedicated infrastructure engineer.
- **Timeline**: Must deliver working async notification delivery within 2 weeks.
- **Budget**: Modest. Managed Confluent Cloud at production scale is not affordable today.
- **Existing stack**: Redis is already in production for sessions and rate limiting. No one on the team has Kafka operations experience.

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams satisfies every functional requirement — consumer groups, ordered delivery, configurable retention, at-least-once semantics — at our current and near-term scale, while radically reducing operational and time-to-value risk compared to Kafka. Our existing Redis instance and team familiarity mean we can ship a working async pipeline in days, not weeks.

Exactly-once semantics for billing notifications will be achieved through application-level idempotency keys (a `notification_id` stored in a PostgreSQL unique constraint on the billing worker). This is the same strategy we would need alongside Kafka's transactional consumer API, because a downstream database write can always fail after the broker has already acknowledged the message — broker-level exactly-once does not eliminate application-level deduplication for our write path. Acknowledging this up front avoids the false confidence that Kafka's transactional API would solve the problem end-to-end on its own.

### Justification by technical property

| Property | Redis Streams | Apache Kafka | Relevance to our case |
|----------|---------------|--------------|----------------------|
| **Throughput** | ~100k–500k msgs/s per stream (single Redis node) | Millions of msgs/s across partitions | Our peak is 500 req/s. Even at 10x (5,000 msgs/s), Redis Streams has >20x headroom. Kafka's ceiling is irrelevant until we exceed it, which is not in the 10x growth plan. |
| **Ordering guarantees** | Strict per-stream (FIFO within a stream) | Per-partition ordering | We partition notifications into streams by entity (e.g., `notifications:project:{id}`), giving per-project ordering. This is sufficient and avoids Kafka's cross-partition ordering gaps. |
| **Message retention** | `MAXLEN` trimming or time-based expiry | Configurable (default 7 days; unlimited possible) | We need retention only until consumers acknowledge — minutes, not days. `MAXLEN ~100000` per stream covers replay after consumer crashes. Kafka's log-compaction and long-term retention are over-engineered for notifications that are fire-and-forget once acknowledged. |
| **Consumer groups** | Native since Redis 5.0 (`XGROUP`, `XREADGROUP`) | Native, mature | Redis consumer groups support the exact semantics we need: group-based partitioning, pending-entry-list for unacknowledged messages, and `XPENDING` + `XCLAIM` for recovery from failed consumers. |
| **Exactly-once semantics** | At-least-once. Application-level dedup required for exactly-once. | Transactional producer/consumer API supports EOS. | Both require application-level idempotency for our use case (see reasoning above). Kafka's EOS prevents duplicate reads; it does not prevent duplicate writes to PostgreSQL if the write fails after commit. We implement idempotency keys either way. |
| **Operational complexity** | Low. Redis is already in production, monitored, backed up. Team has 2+ years of operational experience. | High. Requires broker cluster, ZooKeeper/KRaft, topic management, partition rebalancing, monitoring. Zero team experience. | This is the deciding factor. Kafka is a distributed commit log — running it correctly requires dedicated infrastructure expertise we do not have. Redis Streams adds zero new infrastructure. |

## Consequences

### Pros

- **Fast time to value.** We add `XADD` calls to the existing Flask request handlers and a consumer-group worker process. No new infrastructure to provision, secure, monitor, or back up. Working async delivery in 3–5 days, not 2+ weeks.
- **No new operational surface.** Redis is already in our runbooks, alerting, and on-call rotation. Kafka would require new alerting (under-replicated partitions, consumer lag, broker health), new deployment pipelines, and on-call expertise no one currently has.
- **Sufficient performance.** At 10x current traffic (~5,000 msgs/s), Redis Streams on a single modern node is comfortably within bounds. Sharding by project ID spreads load across streams naturally.
- **Consumer-group recovery.** `XPENDING` and `XCLAIM` let us detect and reclaim messages from crashed workers — the dead-letter and retry mechanism we currently lack.
- **WebSocket foundation.** Redis Pub/Sub (already available) plus Streams gives us both real-time fan-out for WebSocket push and durable processing for email/webhook delivery from the same infrastructure.

### Cons

- **Not a distributed commit log.** Redis Streams lack Kafka's replication-based durability guarantees. If the Redis primary crashes before a replica syncs, unreplicated messages can be lost. Mitigation: we already run Redis with `appendonly yes` and a replica; the practical data-loss window is sub-second, and our billing notifications carry an idempotency key so any lost-and-retried event is safely re-processed.
- **No native schema registry.** Kafka's Confluent ecosystem provides schema evolution for Avro/Protobuf. We will version our notification payloads with an embedded `schema_version` field and validate with Pydantic models — lightweight and sufficient for our internal-only stream.
- **Scaling ceiling.** Single-node Redis Streams top out well before a Kafka cluster. If the platform reaches ~100k MAU with high per-user notification volume, we may need to revisit. At that point, migrating from Redis Streams to Kafka is a well-understood path (consumer lag monitoring, dual-write, cutover), and the team will have grown or hired the infra expertise Kafka demands.
- **Monitoring maturity.** Kafka has richer tooling (Burrow, Kafka Manager, consumer lag dashboards). We will need to build lightweight Redis Stream monitoring (pending-entry count, consumer group lag via `XINFO`) — estimated at 1–2 days of work using our existing Prometheus + Grafana stack.
- **Memory-bound retention.** Unlike Kafka's disk-based log, Redis Streams live in memory (with AOF persistence). Aggressive `MAXLEN` trimming and compact notification payloads (target <1 KB each) keep memory bounded. At 10x scale with 100k messages retained across all streams, we project ~100 MB — well within our Redis instance's capacity.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming. It offers superior throughput, strong replication-based durability, mature consumer-group tooling, and a transactional API for exactly-once processing. However:

1. **Operational cost dominates.** A production Kafka cluster (minimum 3 brokers, KRaft or ZooKeeper) requires dedicated infrastructure expertise for deployment, tuning, partition management, and monitoring. Our team of 6 has zero Kafka experience and no dedicated infra engineer. The risk of misconfiguration — under-replicated partitions, misconfigured retention, consumer-group rebalancing storms — is high and would directly impact notification delivery reliability.
2. **Timeline is incompatible.** Even with managed Kafka (Confluent Cloud, AWS MSK), we would need 1–2 weeks for network setup, IAM, VPC peering, schema design, and team training before writing the first producer — leaving no time for the actual migration. Self-managed Kafka adds another 1–2 weeks for provisioning and hardening. Our 2-week window is for delivering working async notifications, not for infrastructure setup.
3. **Budget constraint.** Managed Confluent Cloud or MSK at our traffic level is affordable, but at 10x growth the cost of a multi-partition, high-throughput Kafka cluster with adequate monitoring becomes significant relative to our infrastructure budget. We would be paying for capacity we will not need for 12–18 months.
4. **Exactly-once is not a differentiator here.** Kafka's transactional consumer prevents duplicate reads, but our billing-notification use case requires idempotent writes to PostgreSQL regardless. The application-level deduplication layer (unique constraint on `notification_id`) is necessary with both brokers and sufficient with both.

Kafka remains the right choice if and when we hit the scaling limits of Redis Streams or when the team grows to include dedicated infrastructure engineers. Re-evaluating at ~100k MAU or when we need long-term event replay for analytics (not just delivery) is appropriate.

### Other alternatives briefly considered

- **RabbitMQ**: Mature, supports dead-letter exchanges and retry queues. But introduces a new operational component (no current team experience, new monitoring, new deployment). Redis Streams already covers our needs without adding a second message broker.
- **AWS SQS + SNS**: Fully managed, zero ops. But introduces a cloud-provider lock-in concern, adds latency (polling-based), and does not provide the consumer-group semantics or ordered delivery we get from Redis Streams. Our on-prem Redis instance also gives us lower latency for real-time WebSocket fan-out.
- **PostgreSQL LISTEN/NOTIFY**: Already in our stack, but no persistence (messages lost on disconnect), no consumer groups, no retry. Solves none of the stated problems.