# ADR-001: Use Redis Streams for the Notification Subsystem

## Status

**Proposed** — 2026-08-11. Pending review by the engineering team before acceptance.

## Context

We run a SaaS project management platform: ~85,000 monthly active users, ~2 million tasks created per month, and a peak of ~500 req/s during business hours. The backend is a Python/Flask monolith (~50k LOC) behind an nginx load balancer, running on four web servers on AWS. Data lives in a single-primary PostgreSQL database (one read replica), and we already operate Redis in production for session storage and rate limiting.

The notifications module sends emails and webhooks when tasks are updated, assigned, or completed — currently **synchronously inside the HTTP request cycle**. This has produced four concrete failures:

1. **Request timeouts**: notification I/O blocks the response. Average latency is 800 ms, spiking to 8 s at peak hours.
2. **Silent failures**: if an email provider or webhook endpoint is down, the notification is dropped — no retry, no dead-letter queue.
3. **Cascading failures**: twice this year, a slow webhook endpoint exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees**: billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, and the synchronous path provides no such guarantee.

The target architecture must decouple notifications from the HTTP request cycle, support retry with exponential backoff, guarantee at-least-once delivery with exactly-once (effectively-once) where feasible, enable real-time WebSocket push within two quarters, and handle 10× traffic growth without a re-architecture.

Hard constraints:

- Engineering team of **6 people** (3 senior, 3 mid-level); **no dedicated infrastructure engineer**.
- **No Kafka experience** on the team today; Redis is already in production and familiar.
- Must deliver value within **2 weeks** of setup/migration work.
- **Modest budget** — managed Confluent Cloud at full scale is not affordable.
- Billing notifications must maintain **exactly-once semantics**.

## Decision

We will use **Redis Streams** as the message backbone for the notification subsystem. Web servers will publish notification events to a Redis stream; dedicated worker processes will consume from consumer groups and perform email/webhook delivery asynchronously, with retry and dead-letter handling.

The decision rests on matching Redis Streams' properties against our actual scale and constraints — not on a generic feature comparison.

- **Throughput**: our load is modest. ~2M tasks/month and 5–10 notifications per task yield an average of ~4–8 notification events/s, with business-hour spikes in the low thousands. Even at 10× traffic growth with generous per-request amplification, sustained rates stay well under 10–20k events/s — a small fraction of what a single Redis node sustains (order of 100k+ small XADD ops/s). Kafka's headline throughput advantage is irrelevant at this scale.
- **Ordering**: a Redis stream is an append-only log with monotonically increasing IDs, so events are totally ordered as published. Consumers within a group receive messages round-robin, so per-entity ordering across a group's consumers is not guaranteed — acceptable for notifications, where email providers do not guarantee delivery order anyway, and mitigable by sharding per-entity streams if it ever matters.
- **Retention**: streams are memory-bound; we will bound them with `XTRIM MAXLEN` and keep only a short in-stream horizon (hours to days), archiving processed notification records to PostgreSQL (already in place) or S3 for the audit trail billing requires. Kafka's long-term log retention buys us replay we do not currently need.
- **Consumer groups**: `XGROUP`/`XREADGROUP`/`XACK` give at-least-once delivery; `XAUTOCLAIM` recovers messages stuck in the pending entries list when a consumer dies; a separate dead-letter stream handles poisoned messages. This covers exactly the retry/DLQ behaviors the synchronous path lacks.
- **Exactly-once semantics**: Redis Streams delivers **at-least-once**, as does Kafka to any external system. True end-to-end exactly-once against email/webhook side effects does not exist on either platform — it must be built from idempotent consumers and a dedupe layer. For billing events we will use the transactional outbox pattern: the billing row and an outbox row are committed in the same PostgreSQL transaction, a relay publishes outbox rows to the stream (idempotent by outbox id), and consumers record delivery outcomes against a unique `processed_events` key. This yields effectively-once delivery, and it is the same mechanism Kafka would require — choosing Redis loses nothing on this requirement.
- **Operational complexity**: Redis is already in production, the team knows it, and `redis-py` is the same client we already use. Adding Streams requires **no new system to operate, no new skills, and no new budget** — the decisive factors given a 6-person team with no infrastructure engineer and a 2-week time-to-value constraint. We will use a dedicated logical DB for streams with `noeviction` and strict `maxlen` so stream data can never evict or be evicted by session/rate-limit data, and move to a small dedicated instance if memory contention appears.

This satisfies every requirement: notifications leave the request cycle (fixing timeouts and pool exhaustion), retries and DLQ handle provider outages (fixing silent failures), the outbox + idempotent consumer gives billing exactly-once, and the same Redis deployment (Pub/Sub on the same infra) supports the WebSocket push goal within the quarter target — all within the 2-week and budget constraints.

## Consequences

**Positive**

- Removes blocking I/O from the request cycle — 800 ms average / 8 s spike latency gone; connection-pool exhaustion can no longer cascade from a slow webhook.
- Retries with exponential backoff and a dead-letter stream turn silent failures into visible, recoverable ones.
- Billing notifications get exactly-once (effectively-once) delivery via the outbox + idempotent-consumer pattern.
- No new infrastructure, no new vendor cost, no new language/runtime — the team ships value in days, well inside the 2-week limit.
- Redis Pub/Sub (already in the stack) is the natural substrate for the WebSocket push work; consumer groups reuse the same cluster.
- Horizontal headroom: a single Redis node covers 10× growth; Redis Cluster is a known, incremental scale-out path if we outgrow it.

**Negative**

- Streams live in memory; retention is bounded by RAM, so long-term replay requires our archive pipeline (Postgres/S3) to be reliable.
- Exactly-once is not provided natively — it depends on the outbox and idempotency layer we must build and keep correct (a weak spot if that discipline slips).
- No automatic key-based partitioning: strict per-entity ordering across multiple consumers in a group requires sharding per-entity streams.
- The pending entries list grows if consumers die without acknowledging; we must monitor it and use `XAUTOCLAIM` with a minimum idle time.
- Operational patterns (retry scheduling, DLQ, poison-message handling) are custom-built from stream primitives rather than provided out of the box — reasonable here, but more code to own than a managed platform would give us.
- Redis is a shared, critical service; colocating streams with sessions/rate limiting widens the blast radius unless we isolate (separate DB, `noeviction`, strict trimming, and eventually a dedicated node).

**Follow-ups**

- Implement the outbox relay and the `processed_events` dedupe table for billing notifications; add tests proving at-least-once delivery under consumer crashes.
- Build the retry/backoff worker (re-queue with exponential delay) and a dead-letter stream with alerting.
- Configure a dedicated logical DB for streams with `noeviction` and `XTRIM MAXLEN`; add memory and pending-entries monitoring dashboards.
- Wire the WebSocket push (Redis Pub/Sub) onto the same deployment; revisit isolation (dedicated node or ElastiCache) if memory contention appears.
- Re-evaluate Kafka only if the platform evolves into a full event-driven architecture (event sourcing, stream processing, long retention, multi-team consumers) or if managed Kafka becomes affordable.

## Alternatives Considered

- **Apache Kafka** — rejected as the primary choice, though not for lack of capability. Kafka is technically superior on durable long-term retention, key-based per-partition ordering, broker-managed consumer offsets, and exactly-once within its own pipeline (idempotent producers + transactions, KIP-98). But none of those advantages pay off here: our throughput needs are two orders of magnitude below Kafka's strengths; per-partition ordering is a feature we do not need; and Kafka's exactly-once does not extend to email/webhook side effects, so the billing guarantee would still be built from an outbox and idempotent consumers — identical work to Redis Streams. What Kafka does cost us is real: a team with zero Kafka experience must provision and operate brokers (EC2 or MSK at several hundred dollars per month, beyond our modest budget), learn topic/partition design, and absorb ongoing JVM/broker operational burden — with no dedicated infrastructure engineer. That setup, on a 6-person team, blows past the 2-week time-to-value constraint. We would choose Kafka if we were building an event-driven platform with event sourcing, stream processing, or long-term replay requirements — none of which are on our roadmap — or if sustained event rates reached hundreds of thousands per second.
- **Keep the synchronous status quo** — rejected. It is the source of all four documented failures (timeouts, silent drops, cascading pool exhaustion, no delivery guarantees); it satisfies none of the scaling targets.
- **PostgreSQL-backed queue** (a notifications table with `SELECT ... FOR UPDATE SKIP LOCKED` polling) — rejected. It works and needs no new infra, but it couples queue throughput to the OLTP primary, competes with task queries for connections and locks, and does not scale horizontally without re-architecting into an external queue anyway. Redis Streams gives us the async queue we need without taxing PostgreSQL.
