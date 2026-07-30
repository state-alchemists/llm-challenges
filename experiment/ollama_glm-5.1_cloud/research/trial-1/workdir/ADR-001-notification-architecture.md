# ADR-001 — Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-07-30
- **Deciders**: Engineering team (6 engineers)
- **Context tags**: notifications, messaging, async, scaling

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, peak ~500 req/s) handles all notification delivery — email and webhooks for task updates, assignments, completions, and billing events — synchronously inside the HTTP request cycle. This has caused four problems as usage grew:

1. **Request timeouts**: Notifications block responses. Average latency 800 ms, spiking to 8 s during peak hours.
2. **Silent failures**: When an email provider or webhook endpoint is down, notifications are dropped with no retry or dead-letter queue.
3. **Cascading failures**: Two incidents this year where a slow webhook endpoint exhausted the database connection pool, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") have no at-least-once or exactly-once guarantee.

We must decouple notifications from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery for all events and exactly-once for billing events, support real-time WebSocket push within two quarters, and absorb 10x traffic growth without re-architecting.

Key constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Existing stack**: Redis already in production for session storage and rate limiting; Python/Flask monolith on PostgreSQL.
- **No Kafka experience** on the team today.
- **2-week delivery window** before the solution must deliver measurable value (reduced request latency, retry on failure).
- **Modest budget**: Cannot afford managed Confluent Cloud at full scale.
- **Exactly-once semantics required** for billing notifications.

## Decision

We will use **Redis Streams** as the message broker for the notification subsystem.

Redis Streams provides sufficient throughput, consumer group semantics, and operational simplicity for our current and projected scale, while requiring no new infrastructure — we already run Redis in production. Application-level idempotency (idempotency keys stored in PostgreSQL) bridges the gap between Redis Streams' at-least-once delivery and the exactly-once requirement for billing events, and this pattern is the same pattern we would need under Kafka anyway.

## Rationale

### Throughput and ordering

Current peak is ~500 req/s; 10x growth targets ~5,000 req/s. Not every request produces a notification, so actual message throughput is a fraction of that. Redis Streams handles 100K+ operations per second on a single instance — over an order of magnitude above our 10x target. Per-stream ordering is guaranteed, which satisfies our requirement that notifications for a given task or user are processed in order.

### Exactly-once semantics

Neither Kafka nor Redis Streams delivers true exactly-once for side effects (sending an email, calling a webhook). Kafka's transactional API guarantees exactly-once across consume-process-produce loops, but the final action — dispatching an email via an external provider — is a side effect outside the transaction. If the process crashes after the email is sent but before the consumer offset is committed, the email is sent again on replay. In practice, production systems build exactly-once on top of at-least-once by using idempotency keys.

Our approach: every notification event carries an `idempotency_key` (derived from `event_type + entity_id + version`). Before dispatching, the worker checks PostgreSQL for a matching key. If found, the notification is skipped as already processed. This pattern works identically with Redis Streams or Kafka — so the exactly-once requirement does not favor Kafka.

### Operational complexity

This is the decisive factor. Kafka (even in KRaft mode without ZooKeeper) requires:

- 3+ broker nodes for production reliability.
- Topic/partition planning, replication factor configuration, and ongoing monitoring.
- A separate operational skill set the team does not have today.
- 2–4 weeks minimum for a team unfamiliar with Kafka to reach production readiness with proper monitoring, failure testing, and runbooks.

Redis Streams uses the Redis instance we already run and monitor. The operational surface area is a single process the team already manages. Consumer group management uses `XREADGROUP`, `XACK`, `XPENDING`, and `XCLAIM` — well-documented commands with first-class support in `redis-py`.

### Delivery timeline

The 2-week constraint makes Kafka unfeasible. Redis Streams integration requires adding stream-producing logic to existing Flask handlers and writing a consumer worker process — both achievable within the window by a team that already operates Redis.

### Cost

Kafka on self-managed infrastructure requires 3+ VMs and significant operational overhead. Managed Confluent Cloud at our projected throughput is disproportionately expensive given the modest budget. Redis adds zero incremental infrastructure cost — it is already provisioned and paid for.

### WebSocket push

Real-time delivery to WebSocket servers within two quarters maps cleanly to Redis Pub/Sub for fan-out, with Redis Streams as the durable source of truth for missed messages on reconnect. Kafka would require additional infrastructure (Kafka Connect, or custom bridge logic) for the same pattern.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming. It offers superior message retention (configurable retention periods, log compaction), more mature consumer group coordination, and native exactly-once semantics for consume-transform-produce pipelines.

We rejected Kafka because:

- **Operational burden is disproportionate.** A 6-person team with no Kafka experience and no dedicated infrastructure engineer would spend weeks on setup, tuning, and incident response procedures. Two incidents this year were caused by cascading failures from synchronous notification processing — we need the fix fast, and Kafka's operational ramp delays that.
- **The 2-week delivery window excludes it.** Reaching production readiness with Kafka (monitoring, failure modes tested, runbooks written) takes 2–4 weeks for an experienced team; longer for one learning it from scratch.
- **Budget constraint.** Managed Confluent Cloud at scale is too expensive. Self-managed Kafka requires 3+ broker VMs plus operational tooling.
- **Throughput advantage is unused.** Kafka's capacity (millions of messages/sec) is 200× our projected 10x peak. We pay complexity for headroom we do not need.
- **Exactly-once does not eliminate the need for application-level idempotency.** Since our exactly-once requirement is for side effects (email/webhook delivery), not for stream-internal state, the same idempotency-key pattern is required regardless of broker. Kafka's EOS does not remove this burden.

We would reconsider Kafka if throughput exceeded ~50K notifications/sec, if we needed multi-service event sourcing with long-term retention, or if the team grew to include dedicated infrastructure engineers.

## Consequences

### Positive

- **Fast time to value.** Redis is already running. Producers and consumers can be implemented within the 2-week window, immediately reducing HTTP request latency by moving notifications out of the synchronous path.
- **No new infrastructure.** Redis is provisioned, monitored, and understood by the team. No new VMs, no new failure domain, no new on-call runbooks for a second distributed system.
- **Sufficient throughput and ordering.** Per-stream ordering and 100K+ ops/sec capacity provide ample headroom for 10x growth (projected peak ~5,000 req/s, with only a subset producing notifications).
- **Natural WebSocket integration.** Redis Pub/Sub + Streams supports the planned real-time push feature without additional message brokers.
- **Cost-neutral.** No incremental infrastructure spending.

### Negative

- **Message retention is limited.** Redis Streams with `MAXLEN` caps stream length; messages are trimmed, not retained indefinitely. We mitigate this by persisting notification events to PostgreSQL (the outbox pattern) before writing to the stream, so the database is the source of truth for history and audit.
- **Consumer group maturity.** Redis Streams consumer groups are less battle-tested than Kafka's. Edge cases around consumer failures and message reclaiming (`XCLAIM`) require careful handling in the worker implementation. We mitigate this with a well-tested worker library, explicit `XPENDING` monitoring, and alerting on stuck messages.
- **At-least-once, not exactly-once, at the broker level.** Redeliveries are possible after consumer crashes. We mitigate this with PostgreSQL-backed idempotency keys, ensuring the application layer achieves exactly-once delivery for billing events despite the broker's at-least-once guarantee.
- **Single point of failure.** A single Redis instance is a SPOF; Redis Cluster or Sentinel adds complexity. We mitigate this by running Redis with persistence (AOF) and a replica, with automatic failover — matching the redundancy we already have for PostgreSQL.
- **Revisit at scale.** If notification throughput exceeds ~50K/sec or we need multi-service event sourcing with weeks-long retention, Redis Streams becomes a limiting factor and we should evaluate Kafka. The outbox pattern and idempotency-key design make this migration straightforward: consumers are decoupled from the broker choice.