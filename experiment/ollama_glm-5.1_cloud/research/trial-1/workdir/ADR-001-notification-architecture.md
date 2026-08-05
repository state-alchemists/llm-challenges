# ADR-001: Notification Subsystem Message Broker

## Status

Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails, webhooks, and upcoming WebSocket pushes — synchronously inside the HTTP request cycle. This causes request timeouts (800ms avg, 8s spikes), silent failures with no retry, cascading connection-pool exhaustion, and no delivery guarantees for billing-critical events.

We must decouple notifications into an async subsystem with retry + exponential backoff, at-least-once delivery (exactly-once for billing events), and headroom for 10x traffic growth plus real-time WebSocket push within two quarters.

Key constraints:
- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infra engineer.
- **Existing stack**: Redis already in production for sessions/rate-limiting. No Kafka experience.
- **Time**: Must deliver value within 2 weeks of starting migration.
- **Budget**: Modest — managed Confluent Cloud at full scale is not affordable today.

## Decision

**Use Redis Streams** for the notification subsystem.

Redis Streams provides consumer groups, message persistence to disk (via AOF/RDB), and at-least-once delivery semantics out of the box. Combined with application-level idempotency keys on billing notifications, it achieves exactly-once semantics without requiring a separate infrastructure investment.

Given a 6-person team with zero Kafka experience and a 2-week delivery window, Redis Streams is the only option that meets the time constraint. The team already operates Redis in production, so the operational surface area — monitoring, backups, alerting, upgrade procedures — is already familiar. Introducing Kafka would require learning a new distributed system, provisioning new infrastructure, and building operational runbooks from scratch, all before shipping the first async notification.

The 10x growth target (5,000 req/s peak) remains well within Redis Streams' single-node throughput ceiling (~500k–1M messages/s on modest hardware), and clustering or a future migration to Kafka can be evaluated when actual traffic approaches that ceiling — which at current growth rates is years away, not quarters.

## Consequences

### Pros

- **Immediate value**: Existing Redis instance means we can ship the first async consumer within days, not weeks. No new infrastructure to provision or harden.
- **Operational simplicity**: One fewer distributed system to monitor, scale, and debug. The team already has Redis runbooks, alerting, and on-call procedures.
- **Sufficient throughput**: Redis Streams handles orders of magnitude more than our 10x growth target. No performance ceiling concern in the near or medium term.
- **Consumer groups**: `XREADGROUP` provides partitioned, fault-tolerant consumption with pending-entry tracking for crash recovery — the core primitive we need for retry logic.
- **Message retention**: `MAXLEN` and time-based retention (`MINID`) give predictable disk usage without unbounded log growth, appropriate for notification events that have a defined useful lifespan.
- **Idempotency path to exactly-once**: Billing notifications carry an idempotency key (e.g., `billing:{org_id}:{event_type}:{period}`). Consumers de-duplicate before processing. This is the standard pattern for exactly-once delivery over at-least-once transports and works reliably with Redis Streams' `XPENDING` + `XCLAIM` for crash recovery.
- **Cost**: No new managed-service spend. The existing Redis instance (or a dedicated notification Redis on the same budget class) covers the load.

### Cons

- **Durability model**: Redis persists to disk asynchronously (AOF every second by default) or synchronously (AOF every write). For billing-critical notifications we must configure `appendfsync always` on the notification Redis instance, which trades some write throughput for durability. Even with `everysec`, the worst case is 1 second of data loss — acceptable for non-billing notifications, and billing events use the stricter setting.
- **Not a distributed commit log**: Redis Streams lacks Kafka's partitioned log with offset-based replay semantics. If we later need multi-consumer replay of the full event history (e.g., a new analytics consumer that reprocesses all historical notifications), we will need to migrate to Kafka or a similar system. This is unlikely within the next 12–18 months given our use case.
- **No native exactly-once**: We achieve exactly-once through application-level idempotency, not broker-level transactional semantics. This is a well-understood pattern but requires discipline: every billing notification consumer must check and set the idempotency key before side-effect execution.
- **Single-node risk**: Without Redis Cluster, a primary failure pauses production until replica promotion. Mitigation: configure Redis Sentinel or run a dedicated notification Redis with automatic failover — still simpler than operating a Kafka cluster.
- **Future migration**: If traffic genuinely exceeds Redis Streams' capacity or we need long-term event replay for analytics, we will need to migrate to Kafka. This is a bounded cost: the consumer-group abstraction is similar, and the migration path (dual-write to both, then cut over consumers) is well-documented. We accept this as a future option, not a present problem.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event streaming platform and would be the correct choice for a larger team with dedicated infrastructure engineering and longer delivery timelines.

**Why we reject it for this decision:**

| Factor | Kafka | Our constraint |
|--------|-------|----------------|
| **Setup time** | 2–4 weeks minimum: broker provisioning, ZooKeeper/KRaft config, topic design, ACLs, monitoring | Must deliver value in ≤2 weeks |
| **Operational expertise** | Requires deep knowledge of partition management, consumer lag monitoring, broker balancing, ISR management | No Kafka experience on team; no dedicated infra engineer |
| **Cost** | Self-hosted: 3+ broker nodes + monitoring. Managed Confluent Cloud: significant monthly spend at scale | Budget is modest; managed option not affordable at full scale |
| **Throughput** | Designed for millions of events/s, multi-TB retention | Our 10x target (~5k req/s) is 2–3 orders of magnitude below Kafka's entry point |
| **Exactly-once** | Native support via idempotent producer + transactions | Valuable, but we achieve the same end result with idempotency keys on Redis Streams |
| **Long-term retention** | Configurable, days to years, with offset-based replay by new consumers | We need retry + backoff, not long-lived event replay. Retention is days, not years |

Kafka is over-engineered for our current and near-term scale, and under-staffed for our operational capacity. The 2-week constraint makes it a non-starter. If the platform reaches a scale where Kafka is justified (dedicated infra team, traffic requiring partition-level parallelism, need for multi-consumer historical replay), we can migrate then — and the consumer-group interfaces we build on Redis Streams will map directly to Kafka consumer groups, minimizing rewrite cost.