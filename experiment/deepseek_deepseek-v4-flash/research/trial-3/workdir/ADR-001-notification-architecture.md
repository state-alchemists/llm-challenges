# ADR-001: Notification Subsystem — Use Redis Streams as the Async Message Backbone

## Status

Proposed

## Context

We run a SaaS project management platform: ~85,000 monthly active users, ~2M tasks
created per month, and a peak of ~500 req/s during business hours. The backend is a
Python/Flask monolith (~50k lines) fronted by 4 web servers behind an nginx load
balancer on AWS, backed by PostgreSQL (single primary, one read replica). Redis is
already in production for session storage and rate limiting.

The notifications module (email + webhooks for task updates, assignments, and
completions) runs **synchronously inside the HTTP request cycle**. That design has
produced four concrete failures:

1. **Request timeouts** — notification delivery blocks the response; average latency
   is 800ms and spikes to 8s during peak hours.
2. **Silent failures** — a downed email provider or webhook endpoint drops the
   notification with no retry and no dead-letter queue.
3. **Cascading failures** — twice this year a slow webhook exhausted the connection
   pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired",
   "payment failed") must be delivered exactly once; the current path has no
   guarantee at all.

We need to decouple notifications from the request cycle, retry with exponential
backoff, guarantee at-least-once delivery for billing events (exactly-once where
feasible), add real-time WebSocket push within two quarters, and absorb 10x traffic
growth without re-architecting.

Constraints that bound the choice:

- Engineering team: **6 people (3 senior, 3 mid), no dedicated infrastructure
  engineer**.
- **Redis is already operated in production**; the team knows it.
- **No Kafka experience on the team today.**
- Must deliver value within **2 weeks** of setup/migration work.
- Modest budget — managed Confluent Cloud at full scale is out of reach.
- Exactly-once semantics for billing notifications must be maintained.

## Decision

**Adopt Redis Streams as the notification message backbone.** Producers in the Flask
request cycle write events with `XADD` and return immediately; a pool of worker
processes consumes them via consumer groups (`XREADGROUP` / `XACK`) and performs the
email/webhook side effects outside the request path. Redis Streams runs on
infrastructure we already operate, in a skill domain the team already has, and
delivers every guarantee the problem statement requires — at a scale where Kafka's
headline advantages are irrelevant.

The load arithmetic makes this unambiguous. ~2M tasks/month is roughly **0.8
notification events/second sustained**; even assuming 10 events per task and 10x
traffic growth, we project a few hundred events/second at peak. A single Redis
instance sustains 100k+ operations/second on modest hardware — **3–4 orders of
magnitude of headroom** at the stated 10x target. Kafka's strengths (millions of
messages/second, replicated log, long retention, exactly-once for broker-internal
flows) are real, but none of them binds at this scale, while Kafka's operational
cost binds immediately for a 6-person team with no Kafka experience.

### Property-by-property comparison

| Property | Redis Streams | Apache Kafka | Verdict at our scale |
|---|---|---|---|
| **Throughput** | 100k+ ops/s on a single node; horizontal via sharded streams | Millions/s; horizontal partitioning | Parity — Kafka's headroom is unused; Redis has 100x+ margin over our 10x target |
| **Ordering guarantees** | Total order within a stream; per-entity order via sharding on `task_id` | Per-partition order; per-entity via key → partition hash | Parity — both require key-based partitioning for per-entity ordering |
| **Message retention** | Manual: `MAXLEN`/`XTRIM`; no automatic expiry; replay while retained | Configurable auto-retention (default 7 days), offset-based replay | Kafka wins — irrelevant here: notifications are short-lived; audit goes to Postgres |
| **Consumer groups** | `XGROUP`/`XREADGROUP` with pending-entry list (PEL), `XACK`, `XCLAIM`/`XAUTOCLAIM` (Redis ≥ 6.2) for crash recovery | Native groups, rebalancing, committed offsets | Parity — both give at-least-once with ack/offset management |
| **Exactly-once semantics** | Not native; achieved as effectively-once via consumer idempotency (dedup by `event_id`) | EOS via transactions, but **only for Kafka→Kafka flows** | Parity in practice — external side effects (SMTP, HTTP) can't be transactional in either |
| **Operational complexity** | Zero new infrastructure; extends existing Redis ops knowledge | 3-broker cluster, KRaft/ZooKeeper, rebalancing, monitoring, disk management, new skills | Redis Streams wins decisively |

### Why exactly-once does not decide this

End-to-end exactly-once against external systems is **not achievable with any
broker**. A consumer that crashes after the email is sent but before the ack is
indistinguishable from one that crashed before sending; the redelivery is inherent
to at-least-once. Kafka's exactly-once semantics cover only producer→broker→consumer
flows where both ends are Kafka. Since our consumers are SMTP and HTTP webhooks,
both options reduce to the same pattern: **at-least-once delivery + idempotent
consumers**. Billing events carry a unique `event_id`; workers deduplicate against a
unique index on `notification_deliveries(event_id, channel)` in Postgres before
sending. That is effectively-once, it satisfies "exactly-once where feasible," and
it makes the EOS property a non-differentiator between the two candidates.

### Target design (sketch)

- **Produce**: after the DB commit, the request handler `XADD`s a JSON event to
  `stream:notif:{task_id % 32}`. No network I/O to email/webhook providers in the
  request path; the 800ms–8s latency tail disappears.
- **Consume**: a pool of workers uses one consumer group per shard, `XREADGROUP` +
  `XACK` after the external side effect succeeds.
- **Retry**: pending entries (`XPENDING`) older than a threshold are reclaimed with
  `XAUTOCLAIM` and retried with exponential backoff; after N attempts they move to a
  dead-letter stream with an alert.
- **Ordering**: sharding on `task_id` preserves per-task ordering (assign → update →
  complete) with multiple workers — the same mechanism Kafka requires via key-based
  partitioning.
- **WebSocket push** (next two quarters): the same stream feeds push consumers, and
  Redis Pub/Sub — already in our operational wheelhouse — handles the fan-out.
- **Durability**: run streams on a **dedicated Redis instance** (cheap at our size)
  with AOF enabled, so session-cache eviction policies never touch the queue and a
  cache-focused instance doesn't share the queue's failure domain.

## Consequences

### Positive

- **Meets the 2-week constraint.** No new infrastructure, no new language or
  operational skill: the team already runs Redis for sessions and rate limiting.
  Producer + consumer + retry can ship in days, not weeks.
- **Near-zero incremental cost.** Reuses the existing Redis deployment; even a
  dedicated small instance is a rounding error next to managed Kafka.
- **Kills the four failure modes.** Request timeouts (async), silent failures
  (retry + dead-letter), cascading pool exhaustion (decoupled workers), and missing
  guarantees (at-least-once + dedup) are all addressed by the same change.
- **Effectively-once for billing.** At-least-once delivery plus `event_id`
  idempotency meets the billing requirement without Kafka's transactional machinery.
- **Per-task ordering preserved.** Sharded streams keep assign → update → complete
  in order, which a naive fan-out queue would break.
- **Transport-swappable.** Workers consume a documented event schema through a thin
  adapter; if we ever outgrow Redis, the same consumer logic ports to Kafka with the
  transport layer replaced.

### Negative (and mitigations)

- **Weaker durability than Kafka.** A single Redis node is not a replicated log;
  with AOF `everysec` there is a sub-second loss window on crash. *Mitigation*:
  enable AOF on the dedicated streams instance (and `always` for the billing stream
  if the write cost is acceptable at our volume); producer-side retry on `XADD`
  error plus consumer idempotency closes the practical gap.
- **No automatic retention.** Streams never expire on their own; without trimming,
  memory grows without bound. *Mitigation*: `XADD ... MAXLEN ~ 100000` and a nightly
  trim job; archive audit-relevant events to Postgres, which we already run.
- **Dead-letter queue is DIY.** Redis has no native DLQ; we build one on
  `XPENDING` age scanning. This is a small, well-understood amount of code.
- **Single-node SPOF for the queue.** Same posture as today's Redis dependency;
  acceptable given our existing operational maturity, and a dedicated instance
  isolates blast radius.
- **Throughput ceiling is lower than Kafka.** Still ~100x above our 10x target, so
  this is a documented revisit trigger, not a current risk.

## Alternatives Considered

### Apache Kafka — rejected

Kafka is the stronger system; it was rejected on fit, not quality.

- **Operational complexity is the disqualifier.** A production Kafka deployment
  means a 3-broker cluster, KRaft (or ZooKeeper) coordination, partition
  rebalancing, offset/lag monitoring, disk sizing and retention tuning, and upgrades
  — for a 6-person team with **no Kafka experience** and no dedicated infrastructure
  engineer. Every broker upgrade and rebalance becomes a project. This violates the
  "2 weeks to value" constraint by itself: standing up, securing, and learning to
  operate Kafka realistically takes longer than that before any notification flows.
- **Budget.** Managed Kafka (Confluent Cloud, or AWS MSK) carries a meaningful
  recurring cost that the budget explicitly rules out at full scale; self-hosting
  merely converts that cost into engineering hours we don't have.
- **The scale doesn't need it.** Kafka's decisive advantages — millions of
  msg/s, replicated log durability, multi-year retention/replay — are all
  irrelevant at our projected few-hundred-events/second peak. Choosing Kafka for
  throughput we will not use for years, while paying its operational cost today, is
  the wrong trade.
- **Exactly-once doesn't discriminate.** Kafka's EOS covers broker-internal flows
  only; our side effects are external, so Kafka still needs the same idempotent-
  consumer pattern we'd build on Redis Streams.
- **The one honest argument for Kafka** — "adopt early to avoid a migration later" —
  is weak here because the migration is cheap: our workers consume a stable event
  schema through a transport adapter, so moving to Kafka later replaces the adapter,
  not the system.
- **Revisit trigger:** if sustained throughput ever approaches ~10k msg/s, if we
  need long-duration in-broker replay/audit, if we go multi-region with cross-region
  replication, or if the team grows an infrastructure function — revisit Kafka.
  Until then, it is deferred, not dismissed.

### PostgreSQL-backed queue — rejected

Using Postgres as the queue (`SELECT ... FOR UPDATE SKIP LOCKED` polling) was
considered because we already run it. It fails on semantics and coupling: no
consumer groups, no pending-list/claiming model (retry logic is hand-built),
polling load on the OLTP primary, and a queue that competes with transactional
traffic for the same connection pool — the very pool that webhook slowness already
exhausts. Redis Streams offers the needed semantics for free on infrastructure we
already run, so Postgres-as-queue buys nothing.

### Status quo (synchronous delivery) — rejected

Keeping notifications in the request cycle contradicts the problem statement
directly: it is the source of the timeouts, the silent drops, and the cascading
pool failures. It is retained only as a transitional fallback for non-critical
channels during the migration window, never as the target architecture.

---

*Decision owner: engineering. Revisit triggers documented in "Alternatives
Considered — Apache Kafka."*
