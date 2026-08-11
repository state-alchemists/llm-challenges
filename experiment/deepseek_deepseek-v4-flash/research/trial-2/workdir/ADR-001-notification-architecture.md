# ADR-001: Notification Architecture — Redis Streams

## Status

Proposed (2026-08-11)

## Context

Notifications (email and webhooks on task update, assign, complete) are currently sent synchronously inside the HTTP request cycle. As the platform has grown, this design has produced four concrete failures:

1. **Request timeouts** — outbound notification calls block the response. Average latency is 800ms with spikes to 8s during peak hours.
2. **Silent failures** — when an email provider or webhook endpoint is down, the notification is dropped. There is no retry and no dead-letter queue.
3. **Cascading failures** — twice this year, a slow webhook endpoint exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, but the current system provides no guarantee at all.

The platform: Python/Flask monolith (~50k lines), PostgreSQL (single primary + one replica), 4 web servers behind nginx on AWS, ~85k monthly active users, ~2M tasks/month, ~500 req/s peak.

Requirements for the notification subsystem:

- Decouple notifications from the HTTP request cycle (asynchronous processing).
- Retry with exponential backoff; no silent drops.
- At-least-once delivery for billing events, exactly-once where feasible.
- Real-time WebSocket push within two quarters.
- Absorb 10x traffic growth without re-architecting.

Hard constraints:

- Engineering team of 6 (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis is already in production (session storage, rate limiting) and the team operates it daily.
- The team has **zero Kafka experience**.
- No more than 2 weeks of setup/migration before delivering value.
- Modest budget — full-scale managed Kafka (Confluent Cloud) is not affordable today.
- Exactly-once semantics for billing notifications must be maintained.

## Decision

**We will use Redis Streams as the notification event backbone.** HTTP handlers will stop sending notifications directly; instead they publish notification events to Redis Streams, and a small pool of worker processes consumes those streams via consumer groups, performs the email/webhook delivery, and acknowledges each message after success. Failed deliveries retry with exponential backoff and eventually move to a dead-letter stream.

The concrete shape:

1. **Streams and sharding** — events are written to streams sharded by entity (hash of `task_id`/`user_id`), so per-entity ordering is preserved while multiple workers consume in parallel.
2. **Consumer groups** — workers use `XREADGROUP`/`XACK`; the Pending Entries List plus `XAUTOCLAIM` (after a visibility timeout) provides crash recovery. A crashed worker's in-flight messages are re-claimed and redelivered — this is the at-least-once foundation.
3. **Exactly-once for billing** — achieved with idempotency keys: every billing event carries a unique event ID, and the worker records delivered IDs (Redis `SETNX` with TTL, or a unique constraint on a Postgres `outbound_deliveries` table) before/after external delivery. True exactly-once to an email/webhook provider is impossible without provider-side idempotency support; idempotent consumers are the standard way to make outbound delivery "effectively once," and this is the same pattern Kafka would require.
4. **Retry + DLQ** — a message that fails is retried with exponential backoff (bounded by a visibility timeout and retry counter); after N attempts it is written to a `dlq:notifications` stream and alerts fire. No more silent drops.
5. **Publish-side durability** — the HTTP handler writes the event to a Postgres outbox table in the same transaction as the domain change; a publisher daemon ships outbox rows to Redis Streams. This prevents losing events between request commit and enqueue.
6. **WebSocket push** — the same Redis cluster serves Pub/Sub (or streams) to a WebSocket gateway within the two-quarter window, reusing existing infrastructure.

### Why this wins, against the constraints

- **Operational complexity (team of 6, no infra engineer)**: Redis is already running in production and the team operates it. Streams are a feature of software we already run — there is no second distributed system to stand up, tune, upgrade, or debug. Kafka would add an entire new cluster (brokers, replication, disk sizing, partition/rebalance management, monitoring) that nobody on the team has run before.
- **Time (2-week budget)**: Redis Streams (consumer groups, `XAUTOCLAIM`, trimming) can be in production in days. A production-grade Kafka deployment plus a team learning curve would exceed the 2-week window.
- **Throughput**: the current peak is ~500 req/s; 10x growth lands at a few thousand notification events/s. A single Redis node sustains orders of magnitude beyond that. Kafka's throughput advantage is not a differentiator at this scale.
- **Ordering**: Redis Streams preserve insertion order per stream; sharding by entity gives per-entity ordering. Kafka gives per-partition ordering. Neither gives global cross-entity ordering without sacrificing parallelism; the guarantees are comparable for our use case.
- **Exactly-once**: Kafka's transactional EOS (idempotent producer + transactions) only guarantees exactly-once for read-process-write *within* Kafka. It cannot make an email/webhook delivery exactly-once without provider idempotency. The billing requirement therefore needs an idempotent-consumer pattern either way — Redis loses nothing here.
- **Cost**: zero incremental infrastructure spend; the budget constraint is untouched.

## Consequences

### Positive

- **Request latency collapses** — handlers only publish to the outbox/stream (milliseconds) instead of calling external providers synchronously; the 800ms average and 8s spikes disappear.
- **No more silent failures** — retries with exponential backoff plus a dead-letter stream make every undelivered notification visible and recoverable.
- **No more cascading failures** — webhook/email work is bounded by worker concurrency with per-provider circuit breakers; a slow webhook can no longer exhaust shared connection pools.
- **Delivery guarantees for billing** — at-least-once with idempotent dedup gives effectively-once delivery for billing-critical events.
- **Small-team operability** — reuses the Redis the team already runs; the whole subsystem is a handful of worker processes and existing tooling.
- **Fast WebSocket path** — the same cluster serves the real-time push requirement within two quarters.
- **10x headroom** — current shape comfortably handles the stated growth target.

### Negative

- **Memory-bound retention**: Redis Streams are memory-resident, not a durable log like Kafka. A long-down consumer or unbounded backlog grows Redis memory and can evict other keys. Mitigations: length/age-based trimming (`XTRIM`), aggressive consumption, a dedicated Redis instance for streams (or at least a separate logical DB), and monitoring of stream length, PEL depth, and consumer lag. The stream is a buffer, not the source of truth — Postgres + the outbox table remain authoritative.
- **Crash durability**: without AOF `everysec`, a crash can lose up to ~1s of published events. Acceptable given the outbox replay path and at-least-once semantics; enable AOF on the streams instance.
- **No native exactly-once**: dedup is our responsibility (as it would be with Kafka for external side effects).
- **Bounded horizontal scale**: the ceiling is a single Redis node (or Redis Cluster, which sacrifices cross-shard ordering). The publisher/consumer abstraction keeps a future transport swap open, but if sustained volume far exceeds 10x, this decision must be revisited.
- **Retry reordering**: a retried message can be delivered after later messages of the same stream. Per-entity sharding and a short retry window make this negligible — notification emails are order-insensitive, and per-task assignment emails rarely conflict.

### Follow-ups

- Transactional outbox table + publisher daemon.
- Worker pool with per-provider circuit breakers and bounded concurrency.
- Idempotency-key generation and dedup store for billing events.
- DLQ alerting and replay tooling.
- Monitoring: stream length, PEL depth, consumer lag, retry counts.
- Define the event schema and versioning now; keep the publish/consume interface thin so a future Kafka migration swaps only the transport layer.

## Alternatives Considered

- **Apache Kafka — rejected (for now, not forever).**
  - **Operational complexity**: the decisive factor. A self-managed Kafka cluster — brokers, replication, disk sizing, partition/rebalance management, upgrades, lag monitoring — added to a 6-person team with no Kafka experience and no infrastructure engineer is the single highest-risk option available. Managed Confluent Cloud is explicitly out of budget at full scale; even AWS MSK would still require the team to learn Kafka's operational semantics and adds recurring cost.
  - **Time**: standing up a production-grade Kafka cluster and reaching competence exceeds the 2-week constraint; Redis Streams ships in days.
  - **Throughput**: not a differentiator at our volume (500 req/s peak, ~2M tasks/month, even at 10x). Redis has headroom for orders of magnitude more.
  - **Exactly-once**: Kafka's transactional EOS applies to Kafka-to-Kafka read-process-write, not to outbound email/webhook delivery; the billing requirement needs the same idempotent-consumer pattern regardless of transport.
  - **Ordering and retention**: Kafka's disk-based retention and per-partition ordering are real advantages, but our retention need is short (hours, not weeks) and our ordering need is per-entity, which streams satisfy.
  - **What would have made Kafka win**: sustained throughput beyond ~100k msg/s, a durable multi-week replayable event log as a product requirement, a multi-team event ecosystem, or an infrastructure engineer plus budget for managed Kafka. If 10x growth becomes sustained massive event volume, revisit with the transport-swap migration the abstraction enables.
- **Status quo (synchronous in-request delivery) — rejected.** It is the direct cause of the latency spikes, timeouts, silent failures, and the two connection-pool incidents; it cannot provide retry, ordering, or exactly-once guarantees, and it cannot survive 10x growth.
- **Managed queue (AWS SQS FIFO) — noted, not evaluated as a primary option.** Worth one line because we are on AWS: SQS FIFO provides per-key ordering and effectively-once, but caps at 300 msg/s and would add a third provider to operate; standard SQS gives only at-least-once with no consumer-group model as strong as streams for our worker pattern. Not competitive with Redis here given the infrastructure we already run.
