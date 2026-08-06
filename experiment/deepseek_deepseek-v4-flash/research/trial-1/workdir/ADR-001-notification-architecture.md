# ADR-001: Notification Architecture — Redis Streams over Apache Kafka

## Status

Proposed — 2026-08-06. Awaiting team review before implementation.

## Context

We run a SaaS project-management platform: 85,000 monthly active users, ~2M tasks
created per month, peak ~500 req/s during business hours (`system_context.md:5-8`).
Notifications — email and webhooks fired on task update, assignment, and
completion — are currently sent **synchronously inside the Flask request cycle**
(`system_context.md:16`). That design has produced four concrete failures
(`system_context.md:20-25`):

1. **Request latency**: every notification adds ~800ms to the response, spiking to
   8s at peak. Billing-adjacent pages suffer the same tax.
2. **Silent failures**: when an email provider or webhook endpoint is down, the
   notification is dropped. No retry, no dead-letter queue.
3. **Cascading failures**: twice this year, a slow webhook exhausted the Postgres
   connection pool and took unrelated features down with it.
4. **No delivery guarantees**: billing-critical notifications ("trial expired",
   "payment failed") must be delivered exactly once; today delivery is best-effort.

The scaling target (`system_context.md:27-34`): decouple notifications from the
request cycle, retry with exponential backoff, at-least-once for billing events
with exactly-once where feasible, real-time WebSocket push within two quarters,
and headroom for 10x traffic without re-architecting.

Binding constraints (`system_context.md:36-43`):

- Engineering team of **6** (3 senior, 3 mid) with **no dedicated infrastructure
  engineer**.
- **Redis is already in production** (session storage, rate limiting).
- **Zero Kafka experience** on the team today.
- Must deliver value in **≤ 2 weeks** of setup/migration.
- **Modest budget** — managed Confluent Cloud at full scale is not affordable.
- Billing notifications must maintain **exactly-once semantics**.

## Decision

We will build the asynchronous notification bus on **Redis Streams**, not Apache
Kafka.

Concrete architecture:

- **Producer.** After a task change commits, the Flask app `XADD`s one event per
  notification to the `notifications` stream with fields `notification_id`,
  `type`, `entity_id`, `recipient`, `payload`. No external call remains in the
  request path — the 800ms–8s latency tax and the pool-exhaustion cascade are
  removed at the producer boundary.
- **Consumers.** A small Python worker service (same client stack the team already
  runs) reads with `XREADGROUP BLOCK` on consumer group `notifier-workers`; each
  entry is delivered to exactly one worker, which performs the email/webhook send
  with exponential backoff, then `XACK`s. Entries stalled past a timeout (dead
  worker) are reclaimed with `XCLAIM`; after N failed attempts an entry is written
  to a `notifications-dlq` stream for review.
- **Delivery guarantee.** Both options are at-least-once at the transport layer;
  neither can be exactly-once to an external provider (see rationale). We achieve
  effectively-once for billing by deduplicating at the consumer: a unique
  `notification_deliveries(notification_id, channel)` constraint in Postgres, plus
  idempotency keys on outbound webhook calls.
- **Isolation.** The bus runs on a small dedicated Redis instance (or, initially,
  a dedicated logical DB on the existing one) so stream traffic and memory cannot
  contend with session/rate-limit traffic. The existing session Redis stays
  untouched either way.
- **Future-proofing.** The producer/consumer boundary is a thin `enqueue` /
  `consume` interface. The Redis semantics map 1:1 onto Kafka (stream ≈ topic,
  consumer group ≈ consumer group), so a later swap to Kafka is a re-implementation
  behind the same interface, not a re-architecture.

### Rationale

- **Load does not discriminate between the options.** At 10x, projected peak is
  roughly 10–25k notifications/s (500 req/s × 2–5 notification events per request,
  scaled 10× — an estimate from `system_context.md:8`). Redis Streams sustains high
  tens of thousands to ~100k `XADD`/`XREADGROUP` ops/s on a single core (typical
  published figures); Kafka's millions-of-messages-per-second ceiling buys nothing
  at this scale. Raw throughput is not the deciding axis here.
- **The team and the deadline decide it.** Kafka's operational surface — broker
  cluster, KRaft quorum, partitions, replication, ISR monitoring, lag tooling — is
  a standing tax that no member of a 6-person team with zero Kafka experience is
  equipped to carry. Standing up Kafka to production grade (retry, monitoring,
  migration) inside two weeks is not credible for this team. Redis Streams is a
  days-long change reusing an operational model the team already runs in
  production.
- **Exactly-once does not favor Kafka.** Kafka's exactly-once semantics
  (idempotent producer + transactions, KIP-98) apply to Kafka-internal
  read-process-write pipelines. They cannot make a webhook HTTP call or an email
  provider delivery transactional. End-to-end exactly-once to an external system
  is impossible with either technology; both are at-least-once, and the real
  guarantee must be built at the consumer with idempotent delivery records.
  Choosing Kafka for EOS would be choosing it for a property it cannot deliver
  here — the one hard requirement does not justify it.
- **WebSocket push synergy.** The two-quarter real-time requirement is naturally
  served by Redis Pub/Sub fan-out to the WebSocket gateway on the same client
  stack. Kafka would need a separate consumer group and new infrastructure for the
  same effect.
- **Retention is not a requirement for notifications.** Notifications are
  transient; replay/audit value is low, and the authoritative record for billing
  already lives in Postgres. Kafka's log retention is a strength we do not need —
  Redis Streams' memory-bounded window is a non-issue if we size `MAXLEN` and
  monitor lag.

## Consequences

### Positive

- **Async decoupling** removes the 800ms–8s request-latency tax and the
  connection-pool cascade (`system_context.md:22-24`).
- **Retry, backoff, and DLQ** become cheap: no new infrastructure, no new
  language, no new monitoring stack.
- **Effectively-once for billing** via at-least-once + consumer dedupe — the
  strongest guarantee achievable to external providers.
- **Near-zero marginal cost**: one small Redis node instead of a Kafka cluster or
  managed Confluent spend.
- **Fits the 2-week constraint**; the team already operates Redis in production.
- **Reversible**: if load or requirements outgrow Redis Streams, the interface
  maps onto Kafka directly.

### Negative

- **Memory-bound retention.** Redis Streams keeps entries only up to `MAXLEN` /
  available memory. A consumer that lags past the trim point loses messages, so we
  must size the cap for worst-case backlog and alert on consumer lag.
- **No time-based replay/audit log** like Kafka's. Anything that needs replay must
  be persisted elsewhere — billing records already are, in Postgres.
- **Ordering under failure.** A single stream is totally ordered, but crash
  redelivery (`XCLAIM` of a stalled worker's pending entries) can interleave and
  reorder delivery. Notifications do not require strict total order, so this is an
  accepted limitation — but it must be a known one.
- **No automatic rebalancing across shards.** One stream + one group scales the
  worker pool by adding consumers, but splitting into multiple streams (manual
  sharding) is our responsibility when we need it. A single stream on one node is
  also a single point of failure — the dedicated instance needs replication
  (multi-AZ) or a documented restore plan.
- **Consumer lag is manual to manage.** Redis has no built-in lag telemetry like
  Kafka's; we must track `XLEN` vs. consumer position ourselves for alerting.
- **Shared-memory risk.** If we reuse the existing Redis instance, unbounded
  stream growth could contend with sessions and rate limiting — hence the
  dedicated-instance recommendation in the Decision.

### Follow-ups

- Provision a dedicated multi-AZ Redis instance via Terraform; set
  `MAXLEN ~1M` with approximate trimming and memory alarms.
- Implement the consumer with exponential backoff, `XCLAIM` stall timeout, DLQ,
  and the Postgres dedupe table for billing events.
- Add lag/`XLEN` dashboards before cutover; keep the synchronous path behind a
  feature flag until the worker has been observed healthy.
- Write the `enqueue` / `consume` interface so Kafka remains a drop-in swap.

## Alternatives Considered

- **Apache Kafka (rejected).** The strongest streaming engine on the table:
  log-based retention and replay, per-partition ordering with keyed partitioning,
  first-class consumer groups with automatic rebalancing, and a throughput ceiling
  orders of magnitude above our peak. It loses on every constraint that actually
  binds: no team experience, no infrastructure engineer, >2 weeks to
  production-grade, and managed Confluent Cloud is explicitly out of budget —
  self-hosting means operating brokers, KRaft, replication, and monitoring with
  six people. Its headline differentiator, exactly-once semantics, does not extend
  to deliveries to external webhook/email providers, so the one hard requirement
  does not justify it. We would have chosen Kafka if we had dedicated platform
  engineers, needed long-term replay/audit at scale, or projected throughput
  beyond a single node's stream capacity.
- **AWS SQS/SNS (scoped out).** Fully managed FIFO queues would satisfy
  at-least-once with near-zero operational effort and would be a legitimate answer
  if managed messaging were in-bounds. Rejected because it would split the
  notification substrate — durable queue in SQS, WebSocket fan-out in Redis — into
  two systems, and because the team already operates Redis, keeping one
  Redis-based pipeline is the lower-operational-surface choice. Worth revisiting
  if the appetite for self-managing anything drops.
- **PostgreSQL as a queue (scoped out).** A `notifications` table polled with
  `FOR UPDATE SKIP LOCKED` needs zero new infrastructure and works at this scale,
  but it couples queue throughput to OLTP database load — the exact pool-exhaustion
  failure mode that motivated this work (`system_context.md:23`) — and adds lock
  churn on the primary at 10x.
