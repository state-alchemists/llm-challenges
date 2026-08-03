# ADR-001: Notification Architecture — Async Delivery with Redis Streams

## Status

Proposed

## Context

We run a SaaS project management platform on AWS. Today: 85,000 monthly active users, ~2M tasks created per month, peak ~500 req/s during business hours. The backend is a Python/Flask monolith (~50k lines) on 4 web servers behind nginx, with PostgreSQL (single primary, one read replica) and Redis (currently used only for session storage and rate limiting).

The notifications module sends emails and webhooks when tasks are updated, assigned, or completed, and it does so **synchronously inside the HTTP request cycle**. That design has produced four concrete failures:

1. **Request timeouts** — notification I/O blocks the response; average latency is 800ms and spikes to 8s at peak.
2. **Silent failures** — an email provider or webhook endpoint being down drops the notification with no retry and no dead-letter queue.
3. **Cascading failures** — twice this year a slow webhook endpoint exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, but nothing enforces that today.

The scaling target: decouple notifications from the HTTP request cycle; retry with exponential backoff; at-least-once delivery with exactly-once where feasible; add real-time WebSocket push within two quarters; and survive 10x traffic growth without re-architecting.

The constraints that bound the choice:

- Engineering team of **6 people** (3 senior, 3 mid-level), **no dedicated infrastructure engineer**.
- **Redis is already in production**; **nobody on the team has Kafka experience**.
- No more than **2 weeks** of setup/migration work before delivering value.
- **Modest budget** — managed Confluent Cloud at full scale is unaffordable.
- Billing notifications **must** maintain exactly-once semantics.

The decision below is evaluated against these constraints first and the raw technology second: an excellent system we cannot operate is worse than a good system we already run.

## Decision

**Adopt Redis Streams for the notification subsystem.** We will decouple notification production from the HTTP request cycle by writing notification events to Redis Streams from the request path, and process them asynchronously with consumer-group workers that implement retry with exponential backoff, a dead-letter queue, and idempotent handling of billing notifications.

Concretely:

- **Producer side:** request handlers stop calling email/webhook clients synchronously. Instead they `XADD` a typed notification event (with a unique `event_id`, `type`, `entity_id`, `payload`) to a stream per notification category (`notifications:email`, `notifications:webhook`, `notifications:billing`). The request returns immediately; notification I/O moves off the critical path.
- **Consumer side:** a pool of worker processes reads via consumer groups (`XREADGROUP`), performs the email/webhook side effect, and `XACK`s only after the outcome is durably recorded. Failures go to a retry path with exponential backoff; entries that exhaust their retry budget go to a dead-letter stream (`notifications:dlq`) for manual inspection.
- **Billing semantics:** billing notifications are at-least-once at the transport layer and **effectively-once at the processing layer**: consumers deduplicate on `event_id` against a unique constraint / idempotency key in PostgreSQL before performing the side effect. This is the honest definition of "exactly once" — no broker, Redis or Kafka, can make a third-party email provider or webhook endpoint transactional, so exactly-once *effect* is achieved by idempotent consumers, not by the transport.
- **WebSocket push (2-quarter horizon):** Redis already sits in the stack; Streams (or Pub/Sub for fan-out) feeds the WebSocket gateway in the same component we are already operating. No new system is introduced for real-time push.

Rollout fits the 2-week budget: **Week 1** — async producer in the request path, consumer-group workers, retry/backoff, DLQ; **Week 2** — idempotency for billing notifications and Redis high availability (below). Real-time push follows in the same quarter.

The technical evaluation that drives the choice, property by property:

| Property | Redis Streams | Apache Kafka | Fit for this system |
|---|---|---|---|
| **Throughput** | Tens of thousands of small ops/s on a single node; horizontally shardable via Redis Cluster | Hundreds of thousands to millions of msgs/s with partitioning across brokers | At 10x growth (~5,000 req/s, roughly 2,000–4,000 notification events/s) Redis Streams uses a small fraction of a single node. Kafka's ceiling is irrelevant at our scale. |
| **Ordering guarantees** | Strict insertion order within a stream; consumer groups deliver each entry to exactly one consumer. Per-entity ordering via sharded streams or single-consumer-per-group | Per-partition ordering only (by message key); global ordering requires one partition, which kills parallelism | Both give the per-task/per-user ordering notifications need. Neither offers global ordering at scale; no delta. |
| **Message retention** | Memory-bound; `XTRIM … MAXLEN ~` keeps the stream within a budget. Retention sized to the retry window + DLQ inspection; durable archive in Postgres/S3 for billing audit | Disk-backed log with time/size retention (default 7 days); replayable from any offset | We need short transport retention and a durable audit trail, not long broker replay. Redis retention is sufficient if sized; Kafka's replay is a feature we do not need. |
| **Consumer groups** | Yes: `XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XAUTOCLAIM` (6.2+). Pending-entries list tracks delivered-but-unacked; abandoned entries are reclaimed. No rebalancing protocol to manage | Yes: mature group protocol with automatic rebalancing and partition assignment | Redis's pull-based model is simpler and matches a worker pool; it removes an entire class of rebalancing incidents a small team would otherwise debug. |
| **Exactly-once semantics** | Not native — at-least-once with acks; exactly-once *effect* via idempotent consumers | EOS via idempotent producer + transactions — but only *within Kafka*; end-to-end delivery to email/webhook still requires idempotent consumers | Identical end-to-end work either way. Kafka's transactions buy nothing for external side effects, so this is not a differentiator. |
| **Operational complexity** | Zero new components: Redis is already in production. Must add HA (Sentinel or Multi-AZ ElastiCache) before billing depends on it — a small, well-understood change that also hardens sessions/rate limiting | Broker cluster (KRaft), replication, partitioning, lag/monitoring, disk sizing, version upgrades. Self-hosted = a permanent ops tax; Confluent Cloud is out of budget | Decisive. A 6-person team with no infra engineer and no Kafka experience cannot absorb a second distributed system for a workload Redis already covers. |

### Why Redis Streams wins here

1. **It honors the team constraint.** Six people, no infra engineer, no Kafka experience. Redis Streams adds **no new component** — the team already runs Redis for sessions and rate limiting. Kafka self-hosted means standing up and then indefinitely operating a broker cluster; that is a permanent tax on a third of the engineering team, and managed Kafka is out of budget.
2. **It honors the time-to-value constraint.** The producer + consumer group + retry + DLQ pattern is days of work, not weeks. A self-hosted Kafka setup (brokers, KRaft, security, deploy pipeline, monitoring) would consume most of the 2-week budget before a single notification ships.
3. **It honors the scale target.** 10x growth lands us at a few thousand notification events per second — comfortably within a single Redis node. The 10x requirement does not need Kafka; the exit ramp (below) covers the case where it ever does.
4. **It honors the real-time requirement.** The WebSocket push capability we must ship in two quarters wants Redis anyway (Pub/Sub fan-out / Streams feeding the gateway). Choosing Redis Streams means the push feature reuses the same infrastructure instead of introducing a second system.
5. **It does not sacrifice exactly-once.** Exactly-once for billing is delivered by idempotent consumers keyed on `event_id` — required identically under Kafka, whose transactions only guarantee atomicity *inside* the broker. Choosing Redis Streams therefore costs us nothing real on the billing front.

## Consequences

### Pros

- **Zero new infrastructure, zero new operational surface.** Redis is already in production; the team knows how to run it.
- **Days-to-value.** The async path, retries, and DLQ ship within the 2-week budget; billing idempotency and HA close out week 2.
- **At-least-once with crash recovery.** Consumer groups + the pending-entries list give redelivery of unacked entries; `XAUTOCLAIM` reclaims work abandoned by dead workers. Failures no longer vanish silently.
- **Retry with backoff and a DLQ are native to the design.** Failed entries route to a retry stream and then a dead-letter stream for inspection — directly fixing the "silent failures" problem.
- **Low cost.** No new managed services, no broker fleet; the existing Redis allocation absorbs the load.
- **Sub-millisecond latency and ample headroom** at current and 10x scale.
- **The WebSocket push path reuses the same component**, avoiding a second technology for the real-time requirement.
- **Simple consumer model.** No rebalancing protocol to babysit — a real win for a team of six.

### Cons

- **Retention is memory-bound.** Redis cannot replay a long log like Kafka can; billing audit needs an archival job that copies processed events to PostgreSQL/S3. This is small, but it is new work.
- **No native exactly-once.** We must build idempotent consumers for billing (dedupe on `event_id` in Postgres). This work is required under Kafka too, but it is on us now and must be treated as a hard requirement, not an afterthought.
- **Availability risk on the current Redis.** If today's Redis is a single node, billing notifications must not depend on it until HA is in place (Sentinel or Multi-AZ ElastiCache) and persistence (AOF) is verified. This is a small infra change, but it is a prerequisite for the billing guarantee — schedule it in week 2, not later.
- **Single-node throughput ceiling.** Fine at 10x; at 100x+ we would shard (Redis Cluster) or revisit Kafka. Mitigation: keep the consumer interface thin and the `event_id`/idempotency design transport-agnostic so a later migration is mechanical, not architectural.
- **Per-entity ordering requires design.** Kafka gives per-key partitioning for free; Redis Streams needs one stream per shard key (or a single consumer per group) to serialize per-entity events. At our volume this is a design decision, not a blocker.
- **In-memory by nature.** Unacked/retained entries live in memory; without persistence (RDB/AOF) and HA, a node failure loses work. Configure persistence and test recovery before billing rides on it.

## Alternatives Considered

**Apache Kafka — rejected.** Kafka is the stronger general-purpose event log, and its rejection is not about capability but about fit:

- **Operations.** Self-hosting Kafka is a second distributed system: brokers, KRaft, replication, lag and JMX monitoring, disk sizing, version upgrades. With no infrastructure engineer and no Kafka experience on a 6-person team, that burden would permanently consume a material share of the team — exactly the failure mode (connection-pool exhaustion taking down unrelated features) we are trying to eliminate, moved one level up.
- **Cost.** Confluent Cloud at the scale we need is unaffordable; AWS MSK still leaves meaningful broker care and monitoring with the team. Redis is already paid for.
- **Scale.** Kafka's defining strengths — massive partitioned throughput, long replayable retention, per-key ordering — are not required at 10x our current volume or for a retry-window retention horizon. We would be adopting complexity for headroom we will not use.
- **Exactly-once is not a differentiator.** Kafka's transactions deliver exactly-once only within Kafka; end-to-end delivery to an email provider or webhook still requires idempotent consumers, exactly as Redis Streams does. The billing guarantee would cost the same engineering either way.
- **Time to value.** Standing up and securing a Kafka cluster would consume most of the 2-week budget before any notification feature shipped.

Kafka becomes the right answer only if the platform outgrows Redis (order-of-magnitude traffic beyond 10x) or if the product evolves into long-term replayable event sourcing. The exit ramp is preserved: our consumer contract (event IDs, idempotency, DLQ) is transport-agnostic, so a future migration is a producer/consumer swap, not a redesign.

**Amazon SQS/SNS — considered and not chosen.** Fully managed, built-in DLQ, zero ops — attractive for a small team on AWS. It loses on two grounds: it adds a new managed dependency instead of reusing Redis we already run, and the ordering/exactly-once variant (FIFO queues) carries throughput limits that complicate the 10x target. Redis Streams also gives us the real-time push substrate the roadmap requires. SQS remains the fallback if Redis high availability proves harder to stand up than expected.
