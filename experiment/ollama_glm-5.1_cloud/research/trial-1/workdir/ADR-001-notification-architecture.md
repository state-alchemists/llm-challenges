# ADR 001 — Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-06-16
- **Deciders**: Engineering team (3 senior, 3 mid-level)
- **Context tags**: notifications, async-processing, message-queue, scaling

## Context

The notification module runs synchronously inside the HTTP request cycle of a Python/Flask monolith serving 85,000 monthly active users at ~500 req/s peak. This causes four production problems:

1. **Request timeouts** — notification dispatch (email, webhooks) blocks responses. Average latency is 800 ms, with spikes to 8 s during peak hours.
2. **Silent failures** — downstream provider outages drop notifications with no retry or dead-letter queue.
3. **Cascading failures** — two incidents this year where a slow webhook endpoint exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications (e.g., "trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

The scaling targets are: decouple notification dispatch from request processing, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), add real-time WebSocket push notifications within two quarters, and absorb 10× traffic growth without re-architecting.

The team has six engineers, no dedicated infrastructure role, existing production Redis (session storage and rate limiting), no Apache Kafka experience, a two-week window before the new system must deliver value, and a modest budget that rules out managed Confluent Cloud at scale.

## Decision

> We will use Redis Streams as the message backbone for the notification subsystem.

The Flask application publishes notification events to Redis Streams via `XADD`. A set of consumer processes (separate from the web workers) read from consumer groups using `XREADGROUP`, dispatch emails and webhooks with retry and exponential backoff, and acknowledge completed messages with `XACK`. Stuck messages are reclaimed via `XCLAIM` on the pending-entry list.

Exactly-once semantics for billing notifications are implemented at the application layer: each billing event carries a unique idempotency key. Before producing the notification, the web worker writes the key to a PostgreSQL `notification_outbox` table in the same transaction as the business state change. The consumer deduplicates against this table before dispatching, ensuring that even under redelivery, no billing notification is sent twice.

## Consequences

### Positive

- **Fast time to value.** Redis is already in production; adding `XADD` / `XREADGROUP` calls requires days, not weeks. The two-week constraint is met comfortably.
- **Low operational burden.** No new infrastructure to provision, monitor, or patch. The team already operates Redis (sessions, rate limiting) and has operational runbooks.
- **Sufficient throughput.** A single Redis instance handles ~500 K–1 M messages/s, well above the current 500 req/s peak and the 10× target of 5,000 req/s.
- **Consumer groups natively supported.** `XREADGROUP` provides group-based consumption, automatic message partitioning across consumers, and a pending-entry list for detecting and reclaiming stuck messages — the building blocks for at-least-once delivery and retry.
- **WebSocket path is clear.** Redis Pub/Sub or Streams can fan out push events to WebSocket server processes. No architectural change is needed when real-time notifications are added in the next two quarters.
- **No additional budget.** Redis is already a paid, operated resource. No new vendor contract or capacity planning cycle.

### Negative

- **No native exactly-once delivery.** Redis Streams provide at-least-once semantics. Exactly-once for billing notifications requires application-level deduplication (the outbox-table pattern described above). This adds a PostgreSQL table and a small amount of consumer-side logic, and it means the exactly-once guarantee is only as strong as the deduplication implementation.
- **Retention is bounded.** Redis Streams use either `MAXLEN` or time-based trimming; messages are evicted when the stream exceeds the configured bound. This is acceptable for notifications (a 7-day retention window covers all retry and audit needs) but unsuitable as a long-lived event log or audit trail. If event-sourcing requirements emerge later, a separate durable store will be needed.
- **Single-instance availability.** The current Redis deployment is a single instance. If it fails, all notification processing halts. Mitigation: Redis Sentinel or Redis Cluster for automatic failover. This is a follow-up task (see below), not a blocker for the initial rollout.
- **Consumer-group offsets are in-memory.** Unlike Kafka's replicated offset commits, Redis consumer-group metadata is lost if the Redis instance loses its data directory (e.g., an `FLUSHALL` mistake). Mitigation: persist Redis to disk with AOF, and treat the PostgreSQL outbox table as the authoritative deduplication source.
- **Future Kafka migration is not precluded** but is not free. The producer/consumer abstraction should hide the transport behind a thin interface so that a future migration to Kafka would require implementing a second adapter, not rewriting business logic.

## Alternatives Considered

### Apache Kafka

Apache Kafka provides a distributed, durable commit log with strict per-partition ordering, replicated consumer-group offsets, and native exactly-once semantics via idempotent producers and transactional APIs. It is the standard choice for organizations processing millions of events per second across multiple consumer teams.

We rejected Kafka because:

- **Operational complexity exceeds team capacity.** A 6-person engineering team with no dedicated infrastructure engineer and zero Kafka experience cannot reliably operate a Kafka cluster (brokers, ZooKeeper or KRaft, topic management, partition rebalancing, monitoring). Production incidents would take longer to diagnose and recover from.
- **Setup time violates the constraint.** Provisioning, hardening, and onboarding onto Kafka takes weeks to months — well beyond the two-week window.
- **Throughput is overspecified.** Kafka's design point (millions of messages/s, multi-terabyte retention) is 2–3 orders of magnitude above our projected peak. We are paying complexity tax for capacity we will not use.
- **Budget.** Self-managed Kafka adds EC2 and EBS costs plus operational headcount risk; managed Confluent Cloud at our scale would cost hundreds of dollars per month before discounts, exceeding the modest budget.

We would choose Kafka if: throughput exceeded 100 K messages/s, the team had Kafka operational experience or a dedicated infrastructure engineer, the budget supported managed Kafka, or the system needed a long-lived event log for event-sourcing or cross-domain replay.

### PostgreSQL LISTEN/NOTIFY

PostgreSQL's built-in `LISTEN/NOTIFY` mechanism was considered as the simplest possible async transport. It was rejected because: messages are not persisted (lost on server restart), there is no consumer-group support, no built-in retry, and no mechanism for backlog processing — all of which are hard requirements for the notification system.