# ADR 001 — Notification Subsystem: Redis Streams over Apache Kafka

- **Status**: Proposed
- **Date**: 2026-06-15
- **Deciders**: Backend engineering team (3 senior, 3 mid-level)
- **Context tags**: notifications, messaging, reliability, scaling

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, 500 req/s peak) handles all notifications — emails and webhooks on task events — synchronously inside the HTTP request cycle. This causes four operational problems:

1. **Request timeouts**: Notification sends block responses. Average latency 800 ms, spiking to 8 s during peak hours.
2. **Silent failures**: When an email provider or webhook endpoint is down, the notification is silently dropped — no retry, no dead-letter queue.
3. **Cascading failures**: Two incidents this year where a slow webhook endpoint exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, but the current system provides no such guarantee.

We need to decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), add real-time WebSocket push within two quarters, and handle 10x traffic growth without re-architecting.

**Constraints:**
- 6-person engineering team, no dedicated infrastructure engineer.
- Redis already runs in production for session storage and rate limiting.
- No Kafka experience on the team.
- Must deliver value within 2 weeks of starting migration work.
- Modest budget — managed Confluent Cloud at our eventual scale is not affordable.

## Decision

> We will use Redis Streams as the message broker for the notification subsystem.

Redis Streams satisfies the throughput and ordering requirements at our scale (current 500 req/s, target 5,000 req/s), provides consumer-group semantics for parallel processing and retry, and leverages infrastructure and operational knowledge the team already has. The exactly-once requirement for billing notifications is met through application-level idempotency keys (notification ID + event type) written into PostgreSQL alongside the stream — not through the broker itself.

Kafka's native transactional exactly-once semantics are superior in isolation, but the operational cost (ZooKeeper/KRaft cluster, broker management, partition planning, monitoring) and the team's zero Kafka experience make it prohibitive given the 2-week delivery constraint and 6-person team without a dedicated infra role.

## Alternatives Considered

- **Apache Kafka** — Rejected because the operational burden is disproportionate to our current needs. Kafka's strengths — durable log retention, partition-level ordering, native exactly-once transactions — matter at volumes and team sizes far beyond ours. Our peak of 500 req/s (target 5,000 req/s) is well within Redis Streams' capacity (~500K msgs/s on a single instance). The 2-week constraint is the deciding factor: standing up a production-grade Kafka cluster (or onboarding a managed offering and learning its operational model) requires weeks of work we do not have and expertise we do not possess. We would choose Kafka if our throughput requirement exceeded ~100K msgs/s, if we needed multi-day log retention for event replay, or if the team included a dedicated platform engineer with Kafka experience.

- **PostgreSQL LISTEN/NOTIFY** — Considered briefly as the lightest-weight option. Rejected because it provides no persistence (messages are lost on disconnect), no consumer groups, no dead-letter queue, and no retry mechanism — it does not meet our reliability requirements.

- **RabbitMQ** — Viable but rejected because it introduces a new operational dependency for no marginal benefit over Redis Streams in our use case. Redis Streams already runs on infrastructure the team manages daily.

## Consequences

- **Positive** — Faster time to value: the team can prototype and ship a working async notification pipeline within the 2-week window using the existing Redis instance and familiar tooling. Operational simplicity: one fewer cluster to monitor, patch, and scale. Consumer groups via `XREADGROUP` / `XACK` / `XPENDING` / `XCLAIM` give us parallel processing, automatic retry, and dead-letter handling out of the box. The path to WebSocket push is straightforward — a lightweight consumer can push to connected Socket.IO clients from the same stream.

- **Negative** — Exactly-once is not provided by the broker; it is an application concern. Billing notifications require a deduplication table in PostgreSQL (notification ID + event type as a unique constraint) to prevent double-sends on replay. This is a well-understood pattern but adds application complexity. Redis Streams' memory-bound retention means we cannot keep months of event history for replay; retention is configured via `MAXLEN` or time-based trimming, and we cap it at what the SLA requires (e.g., 7 days). If the product later needs long-lived event sourcing, we will need to revisit this decision. Scaling beyond a single Redis instance for the streams workload requires Redis Cluster, which introduces cross-slot key constraints on consumer groups — a non-trivial migration.

- **Follow-ups** — (1) Implement a `notification_outbox` table in PostgreSQL with a unique constraint on `(notification_id, event_type)` to serve as the exactly-once guard for billing events. (2) Configure the stream with a `MAXLEN` policy of ~1M entries (~7 days at projected volume) and a `XTRIM` schedule. (3) Build a dead-letter consumer on `XPENDING` entries that exceed the max delivery count. (4) Add a WebSocket push consumer as a separate consumer group once the initial async pipeline is stable. (5) Define metrics and alerts on stream length, consumer lag, and dead-letter volume before going live.