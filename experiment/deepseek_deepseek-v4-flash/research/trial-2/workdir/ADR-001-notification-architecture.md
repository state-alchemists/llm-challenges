# ADR-001: Notification Subsystem — Async Delivery Architecture

## Status

Proposed (2026-07-31)

## Context

The notification module sends emails and webhooks when tasks are updated, assigned, or completed. Today these sends happen **synchronously inside the Flask request cycle**, and that is the root of four production problems:

1. **Request timeouts** — sending blocks the response; average latency is 800ms, spiking to 8s at peak (billing and webhook calls to slow third parties).
2. **Silent failures** — if an email provider or webhook endpoint is down, the notification is dropped. There is no retry and no dead-letter queue.
3. **Cascading failures** — twice this year a slow webhook caused connection-pool exhaustion that took down unrelated request paths.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must be delivered reliably, and ideally exactly once; the current path gives neither.

**Scale today:** 85,000 MAU; ~2M tasks/month; ~500 req/s peak. **Scaling target:** handle 10x traffic without re-architecting, and add real-time WebSocket push within two quarters.

**Constraints that shape the decision:**

- Engineering team is **6 people (3 senior, 3 mid) with no dedicated infrastructure engineer**.
- **Redis is already in production** (session storage, rate limiting); the team operates it today.
- **No Kafka experience on the team.**
- Delivery value must arrive within **2 weeks** of setup/migration work.
- Budget is modest — **managed Confluent Cloud at full scale is not affordable today**.
- Billing notifications must keep **exactly-once semantics**.

The core problem is decoupling: turn a synchronous, failure-prone side effect into an asynchronous, retryable, observable pipeline — without buying an operations burden this team cannot carry.

## Decision

**Adopt Redis Streams as the notification backbone.** The Flask monolith enqueues notification events with `XADD`; a small set of Python worker processes consume them via **consumer groups** and deliver to email/webhook/WebSocket sinks. This replaces the synchronous call path in the request cycle.

Target architecture:

- **Produce:** one stream per event class (e.g., `notify:email`, `notify:webhook`, `notify:ws`) or a single stream with a `type` field; each event carries a stable `event_id` (UUID).
- **Consume:** workers read with `XREADGROUP`, process, then `XACK`. A message stays in the consumer's **Pending Entries List (PEL)** until acked — that is the at-least-once mechanism (redis.io/docs/latest/develop/data-types/streams/).
- **Retry with exponential backoff:** on failure the worker does not ack; a reaper runs `XAUTOCLAIM` (Redis ≥6.2) with a `min-idle-time` that grows per attempt (e.g., 2^n seconds), giving natural exponential backoff with zero timers. After N attempts, `XADD` the event to a `notify:dlq` stream and alert.
- **Exactly-once for billing:** at-least-once delivery + an **idempotent consumer**. The billing worker inserts a delivery record keyed on `event_id` into PostgreSQL with `ON CONFLICT (event_id) DO NOTHING` before performing the side effect; duplicate deliveries are no-ops. This is the only way to get true end-to-end exactly-once for external side effects — see below.
- **WebSocket push (next 2 quarters):** Redis is already in the stack; use Redis **Pub/Sub** for fan-out to WebSocket servers, or a per-user stream as a durable mailbox. No new infrastructure.

### Why Redis Streams wins here

Judged on the technical properties the decision hinges on:

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| **Throughput** | ~100k ops/s order of magnitude on a single node (Redis benchmark); `XADD` is O(1) | Designed for millions of msg/s across a cluster |
| **Ordering** | Total order per stream by entry ID; per-consumer in-order delivery within a group | Per-partition ordering only (no global order) |
| **Retention** | Memory-bound; explicit trimming (`XTRIM MAXLEN`/`MINID`) | Disk-based log; cheap time/size retention, replay from any offset |
| **Consumer groups** | Yes — PEL per consumer, `XACK`, `XAUTOCLAIM` recovery (≥6.2) | Yes — partition-based, offset commits, rebalancing |
| **Exactly-once** | Not native; achieved with idempotent consumers | Native *within Kafka* only (transactions, since 0.11); end-to-end still needs idempotent consumers |
| **Ops complexity** | Already running in prod; add keys, add workers | New cluster, JVM tuning, partitions, rebalancing; new expertise |
| **Cost** | Marginal (memory for trimmed streams) | Managed is unaffordable; self-hosted is a support burden |
| **Time to value** | Days | Weeks+ (infra, learning curve, migration) |

**Throughput.** The numbers do not justify Kafka's horsepower. ~2M tasks/month is ~0.8 tasks/s average; even with several notifications per task and 10x growth, sustained notification volume is on the order of thousands of messages/s — two orders of magnitude under what one Redis node sustains. The bottleneck will be the email/webhook providers, not the queue.

**Ordering.** Per-stream total order plus consumer groups gives us everything the product needs: per-user notification ordering (use a stream keyed by user/event class when order matters). Kafka offers only per-partition ordering — the same practical guarantee, with more moving parts to preserve it.

**Retention.** Notifications are transient: retries need minutes-to-hours, replay needs days at most. Redis `XTRIM` handles that. Kafka's cheap long-term log retention is a real advantage only when you need durable event history for analytics/replay — not a current requirement (see Alternatives).

**Consumer groups.** Both models give competing consumers; Redis's PEL + `XAUTOCLAIM` gives us at-least-once and crash recovery with commands the team already has in its vocabulary. Kafka's group rebalancing is more automatic at scale but is exactly the machinery a 6-person team without Kafka experience would be debugging at 2 a.m.

**Exactly-once is a wash — and that is the decisive point.** Kafka's transactional exactly-once (idempotent producers + transactions, added in 0.11.0.0) guarantees exactly-once **for the read-process-write cycle inside Kafka**; the moment a consumer calls an email provider, a webhook endpoint, or writes to PostgreSQL, duplicates become possible and must be handled by idempotent writes or two-phase commit (Confluent docs, "Message Delivery Guarantees"; ActiveWizards, "Kafka Exactly-Once Semantics Guide"). So the billing requirement forces an idempotency key on **either** choice. Redis Streams + `event_id` dedup in PostgreSQL delivers the same end-to-end guarantee Kafka would, without standing up a cluster to get there.

**Operational complexity and team fit.** This is the tie-breaker. Redis is already a production system this team runs. Streams are a data type on an existing server — no new deployment, no JVM, no partition planning, no broker tuning. Kafka, even in KRaft mode (production-ready since 3.3; ZooKeeper removed in 4.0, October 2024 — kafka.apache.org "Upgrading"), is a new distributed system that a team with no Kafka experience and no infra engineer would own. The 2-week constraint and modest budget make that a non-starter: we would spend the entire window standing Kafka up, with nothing delivered.

## Consequences

### Positive

- **Value in days, not weeks.** Existing Redis + worker code delivers async decoupling, retries, and DLQ within the 2-week window — likely within the first week.
- **No new infrastructure, near-zero marginal ops.** No new expertise, no new alerting surface beyond stream lag/PEL depth, no new vendor bill. The team's Redis knowledge transfers directly.
- **Request cycle decoupled.** `XADD` is sub-millisecond; the 800ms/8s latency leaves the request path. Connection-pool exhaustion from slow webhooks is contained in the workers.
- **Reliable delivery.** At-least-once via PEL; exponential backoff via `XAUTOCLAIM` idle-time; DLQ after N attempts; alerting on DLQ growth.
- **Exactly-once for billing.** `event_id` idempotency in PostgreSQL gives true end-to-end exactly-once for external side effects — the same guarantee Kafka would require building anyway.
- **Ordering preserved** per stream; simple, inspectable mental model (`XRANGE`, `XPENDING` for debugging).
- **WebSocket path is free.** Pub/Sub and per-user streams sit on the same Redis, satisfying the 2-quarter realtime goal without a second system.
- **Scales to 10x.** Thousands of msg/s on one node; headroom is orders of magnitude.

### Negative

- **Retention is memory-bound and manual.** Streams must be trimmed (`XTRIM MAXLEN`/`MINID`) or Redis memory grows without bound; there is no Kafka-style cheap long-term log. Notifications are transient, so this is manageable, but it is a discipline we must build into the workers.
- **Exactly-once is not native.** We must build the `event_id` idempotency layer. (We would have had to build it with Kafka too — but Redis does not even offer the *option* of in-broker transactions.)
- **Single-node write ceiling per stream.** A single Redis node is the write bottleneck; beyond roughly 100k ops/s we would need Redis Cluster (which does not support cross-key consumer-group operations cleanly) or a different system. Far above our trajectory, but it is a ceiling, unlike Kafka's horizontal partition scaling.
- **Consumer rebalancing is less automatic than Kafka's.** New consumers pick up new messages; messages already in a dead consumer's PEL need `XAUTOCLAIM` reaping (Redis ≥6.2). Standard practice, but it is worker code we own.
- **Fewer ecosystem tools.** No Kafka Connect, no stream-processing framework; we write the workers and any connectors ourselves. With 6 people and one subsystem, that is acceptable.
- **Migration risk later.** If the platform evolves into event sourcing, analytics replay, or very high fan-out, Redis Streams will be the wrong tool and we migrate to Kafka behind the `enqueue()` abstraction. The producer interface is small; the migration is contained to the consumer side.

## Alternatives Considered

### Apache Kafka — rejected

Kafka is the industry-standard event backbone and wins decisively on three axes: sustained throughput (millions of msg/s), cheap long-term retention with replay, and an ecosystem (Kafka Streams, Connect, monitoring). Its transactional exactly-once (since 0.11) is a genuine differentiator **inside** the broker.

It is rejected for this decision on four grounds:

1. **Operational complexity vs. team.** A 6-person team with no Kafka experience, no dedicated infra engineer, and a 2-week delivery window cannot safely own a Kafka cluster — even KRaft simplifies the metadata layer, it does not remove tuning, partition planning, rebalancing incidents, or the learning curve. Every hour spent operating Kafka is an hour not spent on the product problem.
2. **Cost.** Managed Confluent Cloud is explicitly out of budget. Self-hosting Kafka on EC2 trades money for the exact operational burden above; AWS MSK removes ZooKeeper-style ops but still adds cost and a managed-cluster surface the team has never run.
3. **Overkill for the load.** Our 10x target is thousands of messages/s. Kafka's headline throughput is irrelevant headroom that we would pay for in ops.
4. **Exactly-once does not transfer to our side effects.** Billing "exactly-once" is an end-to-end property that ends at an email provider or a webhook — Kafka transactions cannot make a third-party API idempotent. We would build the same `event_id` idempotency on top of Kafka that we build on Redis Streams, neutralizing the one feature that would have justified the operational cost.

**Revisit trigger:** adopt Kafka when the platform needs (a) sustained >100k msg/s, (b) durable event history with replay beyond days (analytics, event sourcing), (c) many independent consumer groups over the same events, or (d) stream processing with Kafka Streams/ksqlDB. Until then, keep the producer API behind a small `enqueue_event()` abstraction so the consumer side can be re-pointed without touching the Flask monolith's call sites.

### (Considered and folded in) Direct queue libraries / Postgres LISTEN-NOTIFY

Rejected for the same reasons the status quo fails: no durable PEL-style recovery, no consumer groups, and LISTEN-NOTIFY does not persist messages — a restart loses notifications, which is the exact silent-failure class we are eliminating.
