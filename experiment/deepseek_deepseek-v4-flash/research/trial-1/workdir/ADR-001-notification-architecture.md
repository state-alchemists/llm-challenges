# ADR-001 — Notification Architecture: Redis Streams over Apache Kafka

- **Status**: Proposed
- **Date**: 2026-08-11

## Context

We run a SaaS project-management platform serving 85,000 monthly active users, ~2M tasks created per month, and ~500 req/s at peak. The backend is a Python/Flask monolith (~50k lines) with PostgreSQL (single primary + one replica), four web servers behind nginx on AWS, and Redis in production for sessions and rate limiting. Notifications (email + webhooks fired when tasks are updated, assigned, or completed) are currently sent **synchronously inside the HTTP request cycle**.

That design has broken in four ways as usage grew:

1. **Request timeouts** — notification delivery blocks the response; average latency is 800ms and spikes to 8s at peak.
2. **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry and no dead-letter queue.
3. **Cascading failures** — twice this year a slow webhook exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must not be lost, but today they are fire-and-forget.

The scaling target forces a decision now: decouple notifications from the request cycle into async processing; support retry with exponential backoff; guarantee at-least-once delivery, with exactly-once where feasible for billing; add real-time WebSocket push within two quarters; and absorb **10x traffic growth without re-architecting**.

The binding constraints are:

- Engineering team of **6** (3 senior, 3 mid-level), **no dedicated infrastructure engineer**.
- **Redis is already in production** (session storage, rate limiting) and the team operates it today.
- **No Kafka experience on the team.**
- Setup/migration must deliver value within **2 weeks**.
- Budget is modest — managed Confluent Cloud is unaffordable at full scale.
- Billing notifications must be exactly-once.

## Decision

**We will decouple notifications from the HTTP request cycle using Redis Streams with consumer groups**, running on the Redis instance we already operate, fronted by a transactional outbox in PostgreSQL as the durable source of truth, with idempotent consumers at the sink to achieve exactly-once observable behavior for billing notifications.

The intended shape of the subsystem:

- The API layer writes a `notification` row in the same PostgreSQL transaction as the task mutation (transactional outbox), then a lightweight publisher appends the event to a Redis stream. The outbox is the recovery mechanism — nothing is lost even if Redis loses buffered data in a crash.
- Separate streams per notification class: `events:email`, `events:webhook`, `events:billing`. Billing stays isolated so it can be tuned and monitored independently.
- Workers consume with `XREADGROUP` (one stream entry delivered to exactly one consumer per group), acknowledge with `XACK`, and reclaim entries from crashed consumers with `XCLAIM` after a visibility timeout. Entries that exhaust their retry budget (tracked via a delivery-count hash) are moved to a `dlq:` stream that pages the on-call channel.
- Retry uses exponential backoff; webhook and email delivery are idempotent at the sink (dedupe on `notification_id`; idempotency keys on webhook payloads), which is what makes at-least-once delivery behave as exactly-once to the outside world.

**On exactly-once (the one point worth stating plainly):** no broker can guarantee exactly-once *delivery of a side effect* — the failure domain extends past the broker into the email provider and the webhook receiver, and Kafka is no exception. Kafka's transactional semantics (KIP-98) remove duplicates *within* the Kafka pipeline, but the email/webhook send itself remains at-least-once + dedupe. So both options converge on the same sink design: **at-least-once transport + idempotent consumer = effectively-once from the billing system's point of view.** This satisfies "exactly-once where feasible" without buying Kafka's complexity to get there.

### Why Redis Streams wins for us

| Property | Redis Streams | Kafka | Verdict |
|---|---|---|---|
| **Throughput** | ~100k+ ops/s per node; tens of thousands of stream writes/s; scales by sharding streams across instances | Millions of msg/s across a partitionable cluster | At 10x traffic our peak is ~1k–20k msg/s — Redis has 5–100x headroom; Kafka's ceiling is surplus |
| **Ordering** | Strict insertion order within a stream (monotonic entry IDs); one stream = global order | Order only within a partition; needs key-based partitioning for per-entity order | Redis is simpler for the per-task ordering we need |
| **Message retention** | In-memory with `MAXLEN` trimming; AOF/RDB persistence; short-horizon replay only | Log-based disk retention (days/months), full replay from any offset | Kafka wins here; Redis requires archiving (see Consequences) |
| **Consumer groups** | Native since Redis 5.0: `XGROUP`, `XREADGROUP`, `XACK`, `XCLAIM`, pending-entries list; no auto-rebalancing | Mature groups with automatic rebalancing and committed offsets | Comparable; Redis's model is manual but small and well-documented |
| **Exactly-once semantics** | No native EOS — at-least-once + idempotent sink | Transactional EOS *within* the pipeline, but still at-least-once at the external sink | Effectively a tie; both end at idempotent sinks |
| **Operational complexity** | Zero new infrastructure — it is the Redis we already run and monitor | New cluster (brokers, KRaft/ZooKeeper, partitions, rebalancing, monitoring) or managed cost we can't afford | Decisive advantage for a 6-person team with no infra engineer |

The decision follows directly from the constraints: every functional requirement (async decoupling, retry/backoff, at-least-once, consumer groups, WebSocket-ready) is met by Redis Streams, and the operational constraint (6 people, no Kafka experience, 2-week budget, modest spend) is met only by Redis Streams.

## Consequences

### Positive

- **Fastest path to value**: no new infrastructure, no new language, no new vendor — the team ships the first stream + worker within the 2-week budget instead of spending it on cluster bring-up.
- **Low operational burden**: reuse the existing Redis runbook (backups, monitoring, failover). The team already knows how to keep Redis healthy; nothing new to learn under pressure.
- **Fits the budget**: no Confluent/MSK spend; Redis is already paid for and licensed.
- **At-least-once with retry and DLQ**: the PEL + `XACK`/`XCLAIM` mechanism gives crash recovery and redelivery; the DLQ stream ends silent failures and pages humans on poison messages.
- **Ordering is free**: a single stream per class preserves insertion order end-to-end without partition-key thinking — important for per-task update sequences.
- **Composes with the WebSocket plan**: Redis Pub/Sub is the canonical fan-out mechanism for WS gateways; Streams add durable delivery on top. The two-quarter WebSocket push target is *easier* with Redis than with Kafka (which would need a separate WS gateway path anyway).
- **Outbox + archive discipline**: the Postgres outbox and S3 archiving give a durable audit trail independent of Redis memory.

### Negative

- **Memory-bound retention**: streams live in RAM (AOF/RDB for durability). We must bound the backlog with `MAXLEN` trimming and accept short-horizon replay; a long retention horizon (days) at high volume is infeasible. **Mitigation**: keep the backlog bounded to what consumers drain (hundreds of MB), archive raw events from the outbox to S3 for audit/replay needs.
- **No native exactly-once**: duplicates are possible on redelivery after a consumer crash (standard at-least-once behavior). **Mitigation**: sink idempotency keyed on `notification_id`, which is required under either option.
- **Single-node write bottleneck at extreme scale**: Redis serializes writes on its event loop; sharding streams across instances works but breaks cross-stream ordering. **Mitigation**: this bites only far beyond our 10x target (~>100k msg/s sustained); the producer/consumer abstraction keeps a Kafka migration mechanical if we ever get there.
- **Manual consumer-group mechanics**: no automatic rebalancing — a dead consumer's in-flight entries are reclaimed only when `XCLAIM` fires. **Mitigation**: standard visibility-timeout loop (~50 lines) plus lag monitoring on the pending-entries list.
- **Durability windows**: default `appendfsync everysec` can lose up to ~1s on a hard crash. **Mitigation**: the Postgres outbox replays anything Redis loses, and billing's stream can be tuned (`appendfsync always`) independently.

### Follow-ups

1. Land the outbox table + publisher in the monolith; publish on the existing task-update path.
2. Ship `events:email` and `events:webhook` workers with `XACK`/`XCLAIM`, exponential backoff, and a `dlq:` stream + alert.
3. Add idempotency keys to billing webhooks and dedupe on `notification_id`; verify billing delivery with a dry-run fixture suite.
4. Stand up the WebSocket gateway on Redis Pub/Sub (streams unchanged).
5. Archive outbox events to S3; add PEL lag and consumer-health dashboards.

## Alternatives Considered

**Apache Kafka** — rejected. Kafka is the stronger *system* on raw capability: log-based disk retention and full replay, automatic consumer-group rebalancing, partitioning for unbounded horizontal scale, and transactional exactly-once within the pipeline. But every one of those strengths is mismatched to our situation. Throughput: our 10x target peaks at ~1k–20k msg/s; Kafka's millions-of-msg/s is capacity we cannot use and must still operate. Retention/replay: we need bounded, hours-scale replay plus S3 archiving — not week-long broker-side logs. Exactly-once: as shown above, Kafka still requires the same idempotent sink for external delivery, so it buys no guarantee we can't get on Redis Streams. And the decisive blockers are the constraints: a 6-person team with **no Kafka experience and no infrastructure engineer** would be responsible for a new cluster (brokers, KRaft or ZooKeeper, partition/replication tuning, rebalancing incidents, JMX monitoring, disk sizing) — far more than the 2-week setup ceiling, with real incident risk; self-hosting is a full-time job we don't have, and managed options (MSK's infrastructure overhead, Confluent Cloud's price) exceed the modest budget. Finally, Kafka would not remove the need for Redis: the WebSocket push plan still wants Redis Pub/Sub for real-time fan-out. **We would have chosen Kafka only if our sustained throughput demanded broker-side horizontal sharding and week-scale retention (roughly 100x+ our projected load), or if we had dedicated infrastructure headcount to operate a cluster.**

**Celery (or a comparable task-queue framework) on the existing Redis broker** — rejected at the framing stage, briefly noted for completeness. Celery delivers async processing and retries, but its Redis transport has no consumer-group/offset model, no per-stream ordering, and no native DLQ semantics, so we would still hand-build delivery guarantees on a weaker foundation — and we would add a second framework layer (broker, result backend, worker fleet, monitoring) to operate. The decision is not "task queue vs. stream" but which *broker semantics* we build the durable delivery path on; that is the Redis Streams model.
