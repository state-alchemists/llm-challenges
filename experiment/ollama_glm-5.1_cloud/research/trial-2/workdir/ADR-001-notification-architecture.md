# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

**Status:** Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails and webhooks on task updates, assignments, and completions — **synchronously inside the HTTP request cycle**. This has caused:

1. **Request timeouts**: Average notification latency 800 ms, spiking to 8 s during peak hours.
2. **Silent failures**: No retry or dead-letter queue; down-stream outages silently drop notifications.
3. **Cascading failures**: Two incidents this year where slow webhook endpoints exhausted the DB connection pool, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") have no at-least-once or exactly-once guarantee.

We must decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once (and exactly-once where feasible) delivery for billing events, support real-time WebSocket push within two quarters, and handle 10× traffic growth without re-architecting.

**Hard constraints:**

- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already in production (sessions, rate limiting); no Kafka experience.
- Maximum 2 weeks of setup/migration before the system delivers value.
- Modest budget — managed Confluent Cloud at full scale is not affordable today.
- Exactly-once semantics required for billing notifications.

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams meets every constraint: it is already in our runtime, the team has operational experience with Redis, it can be production-ready in days rather than weeks, and at our scale (5,000 req/s at 10× growth) it delivers throughput an order of magnitude above what we need. Exactly-once delivery for billing events will be achieved through an **idempotent-consumer pattern** (idempotency keys + PostgreSQL dedup table) layered above the stream, which is the same approach we would need on Kafka for our use case — Kafka's transactional exactly-once semantics apply to intra-Kafka consume-transform-produce loops, not to external side effects like sending email.

## Consequences

### Pros

- **Fast time-to-value.** Redis is already deployed and monitored. Adding a Streams-based consumer group requires days of work, not weeks. This is the dominant constraint — the team must ship within 2 weeks.
- **Low operational overhead.** No new infrastructure to provision, monitor, or patch. We extend our existing Redis instance (or add a dedicated one for isolation) rather than introducing a distributed commit log with brokers, controllers, and ZooKeeper/KRaft.
- **Sufficient throughput.** Redis Streams handles 100K+ messages/s on a single node. Our 10× peak (≈5,000 req/s) uses ~5% of that headroom. Even accounting for fan-out (one task event producing multiple notification messages), we are well within capacity.
- **Consumer groups built-in.** `XREADGROUP` + `XACK` provides partitioned, load-balanced consumption across our 4 web servers, with automatic message claiming for crash recovery — the core primitive we need for async processing.
- **Per-stream ordering.** Messages within a single stream are strictly ordered by insertion time, which preserves causal order for notifications belonging to the same entity (e.g., all notifications for task #1234 can be routed to one stream or one partition key).
- **Cost efficiency.** No additional licensing or managed-service fees. A second Redis node for isolation (recommended) costs a fraction of even a small Confluent Cloud cluster.
- **Team velocity.** The team already operates Redis in production. Learning `XADD`, `XREADGROUP`, `XACK`, and `XAUTOCLAIM` is a day's work. Kafka's partition/offset/compaction/rebalance mental model would take significantly longer to internalize safely.

### Cons

- **No native exactly-once semantics.** Redis Streams provides at-least-once delivery; consumers may see duplicates after a crash-rebalance. **Mitigation**: Billing notification handlers will use idempotency keys (stored in a PostgreSQL dedup table) to ensure exactly-once *effect*. This is explicit, auditable, and the same pattern we would implement on top of Kafka for external side effects — Kafka's transactional API does not guarantee exactly-once delivery to SendGrid or Stripe.
- **Limited message retention.** Redis Streams are bounded by `MAXLEN` or memory, not the persistent, configurable log retention of Kafka. **Mitigation**: We set a generous `MAXLEN` (e.g., 1M entries ≈ days of backlog) and persist notifications to PostgreSQL before enqueuing. The stream is a dispatch mechanism, not the system of record.
- **No native dead-letter queue.** Kafka has DLQ patterns via topic routing; Redis does not. **Mitigation**: After N retry attempts with exponential backoff, the worker moves the message to a `notifications:dead` stream and alerts. This is straightforward to implement.
- **Single-node availability.** A standalone Redis instance is a single point of failure. **Mitigation**: Deploy Redis with a replica and automatic failover (Redis Sentinel) — or use AWS ElastiCache which provides this out of the box. Our existing Redis already uses a managed setup.
- **Not ideal for very long retention or replay.** If we later need months of event history for analytics, Redis Streams is the wrong tool. **Mitigation**: We don't have that requirement today. If it arises, we can add a Kafka or a dedicated event store downstream without changing the notification dispatch path.
- **Fan-out scaling limit.** Redis Streams does not scale horizontally via partitioning in the same way Kafka topics do — a single stream is a single partition. **Mitigation**: Shard by channel (e.g., `notifications:billing`, `notifications:webhook`, `notifications:websocket`) to parallelize consumption. At our projected load, this is sufficient. If we exceed it, we can shard further by tenant or hash range.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming and would be the correct choice for a larger engineering organization with dedicated infrastructure support.

**Why we reject it for this decision:**

| Factor | Kafka | Assessment |
|--------|-------|------------|
| Team experience | None | The team has zero Kafka operational experience. Misconfiguration of consumer groups, offset management, and partition rebalancing is a common source of outages for new adopters. |
| Setup time | Weeks | A production Kafka cluster (3+ brokers, KRaft/ZooKeeper, monitoring, alerting) requires significant configuration and testing. This exceeds the 2-week delivery constraint. |
| Operational complexity | High | Brokers, controllers, partition management, compaction, replication factor tuning — all require ongoing expertise. We have no dedicated infrastructure engineer. |
| Budget | Prohibitive at scale | Self-hosted Kafka on AWS requires at least 3 m5.xlarge instances plus EBS, plus operational overhead. Managed Confluent Cloud at our current scale starts at ~$300/month for a basic cluster and scales up quickly — the problem statement explicitly rules this out. |
| Exactly-once for billing | Transactional API covers intra-Kafka only | Kafka's exactly-once semantics (idempotent producer + transactions) guarantee exactly-once *within* Kafka. Delivering to an external system (email, webhook) still requires idempotent consumers — the same pattern we implement on Redis. |
| Throughput | Excellent (millions msg/s) | Vastly over-provisioned for our load. We need ~5,000 msg/s at 10× growth. Redis Streams handles this; Kafka's throughput advantage is not a differentiator here. |

Kafka becomes the right choice if we later adopt an event-driven architecture across multiple domains (audit log, analytics, CQRS projections) and have the team capacity to operate it. That is not our current situation.

### Other alternatives briefly considered

- **RabbitMQ**: Good for task queues with dead-letter exchanges, but no native consumer-group rebalancing for our multi-server fan-out. Adds a new infrastructure component with no team experience. Does not justify itself over Redis Streams given we already run Redis.
- **SQS + SNS**: Fully managed, cheap, and scales infinitely. However, SQS does not guarantee ordering within a queue, and achieving exactly-once processing requires the same idempotent-consumer pattern. Introduces a cloud-vendor lock-in concern and adds a new operational surface (IAM policies, DLQ configuration, Lambda/Daemon consumers) for a team with no dedicated infra. Simpler than Kafka, but still more operational surface than extending our existing Redis.
- **Database-queued jobs (e.g., SKIP LOCKED)**: Using PostgreSQL as a queue avoids a new dependency but is inferior for our scaling target. Polling `SKIP LOCKED` at high concurrency creates lock contention, and it cannot efficiently support fan-out to multiple consumer groups. Suitable for small-scale job queues; not for a notification pipeline at our growth target.