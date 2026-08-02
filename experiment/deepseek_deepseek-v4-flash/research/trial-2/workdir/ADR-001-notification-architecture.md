# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

## Status

Proposed

## Context

We run a SaaS project management platform (85,000 monthly active users, ~2M tasks
created per month, peak ~500 req/s during business hours) on a Python/Flask
monolith (~50k lines), PostgreSQL (single primary, one read replica), and four
web servers behind an nginx load balancer on AWS. Redis is already in production
for session storage and rate limiting.

Notifications (email and webhooks on task update/assign/complete) are currently
sent synchronously inside the HTTP request cycle. This causes four concrete
problems:

1. **Request timeouts** — sending blocks the response. Average latency 800ms,
   spiking to 8s at peak.
2. **Silent failures** — a down email provider or webhook endpoint drops the
   notification with no retry and no dead-letter queue.
3. **Cascading failures** — twice this year a slow webhook exhausted the
   connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired",
   "payment failed") must be delivered exactly once; today they are fire-and-forget.

We must decouple notification delivery from the HTTP request cycle, support
retry with exponential backoff, guarantee at-least-once delivery for billing
events (exactly-once where feasible), add real-time WebSocket push within two
quarters, and absorb 10x traffic growth without re-architecting.

Hard constraints:

- Engineering team of **6 people** (3 senior, 3 mid-level), **no dedicated
  infrastructure engineer**.
- **No Kafka experience on the team today**; Redis is already operated in
  production.
- Must deliver value within **2 weeks** of setup/migration work.
- **Modest budget** — managed Confluent Cloud at full scale is not affordable.
- Exactly-once semantics for billing notifications must be maintained.

## Decision

**Adopt Redis Streams as the notification backbone.** Producers write
notification events with `XADD` (non-blocking, sub-millisecond) instead of
calling email/webhook providers inline; a small worker pool consumes them with
consumer groups (`XREADGROUP`), and acknowledgements (`XACK`) drive
at-least-once delivery with retry and exponential backoff. Failed events after a
max-attempt threshold are written to a dead-letter stream for inspection and
re-drive. Billing events carry a unique event ID and are deduplicated on the
consumer side (unique constraint in PostgreSQL), which yields effective
exactly-once delivery.

This decision is driven by the team and budget constraints, not by a
throughput shortfall — and it is the correct trade-off because the two systems
differ almost entirely on properties we do not need, while converging on the
properties we do.

**Why the throughput case is not the deciding factor.** Our projected load is
tiny by broker standards. ~2M tasks/month yields roughly 4–10M notification
events/month (assuming 2–5 events per task) — an average of a few events per
second and, at peak, low thousands of messages per second. Even 10x growth
lands in the tens of thousands of messages per second. Redis Streams on a
single node sustains on the order of 100k+ writes/sec (far more with
pipelining; exact numbers depend on payload size and hardware), so we retain
one to two orders of magnitude of headroom at 10x scale. Kafka's million-plus
messages-per-second capacity is simply not load we will ever approach here;
its cost is paid in operations, not throughput.

**Why the exactly-once case is not the deciding factor either.** Kafka's
transactional exactly-once semantics (EOS) guarantee exactly-once *within
Kafka* — idempotent producers and transactional consumers across topics. They
do not extend to external side effects. Sending an email or invoking a
webhook is an I/O call outside the broker's transaction scope; no broker can
make an external HTTP call exactly-once. The only mechanism that achieves
exactly-once for billing notifications is consumer-side idempotency — a unique
event ID and a dedupe on the durable record (a unique constraint in
PostgreSQL). That mechanism is byte-for-byte identical whether the broker is
Kafka or Redis Streams, so Kafka's flagship feature buys nothing for our
hardest requirement. What remains is an at-least-once delivery contract from
both systems, and both deliver it equivalently: Kafka via committed consumer
offsets, Redis Streams via the per-consumer pending entries list (PEL) with
redelivery through `XCLAIM`/`XAUTOCLAIM`.

**What actually decides it: operations, time-to-value, and team size.** Redis
Streams runs on infrastructure we already run, with commands our team can
learn in a day. Kafka means standing up and operating a distributed JVM
cluster — brokers, KRaft metadata, partition and rebalance tuning, JMX
monitoring, disk and replication management — with nobody on the team whose
job that is. A self-hosted Kafka cluster is a known operational trap at
6-engineer scale, and managed Confluent Cloud is explicitly out of budget.
Redis Streams goes from zero to production value in days, comfortably inside
the 2-week constraint; Kafka realistically cannot be stood up, learned, and
migrated onto in that window by a team with no prior exposure.

**The WebSocket roadmap fits naturally.** Real-time push within two quarters
can be built on the same Redis instance: one consumer group per connected
client for reliable fan-out, or Pub/Sub for broadcast — no new component.

**The choice does not foreclose Kafka.** The worker abstraction (poll →
process → acknowledge) is identical in both systems. If we ever outgrow
Redis Streams — multi-GB/day event volume or long-term replay requirements
that memory-bound retention cannot serve — migrating means swapping the
consumer client and standing up brokers, while the pipeline architecture,
worker code shape, and idempotency layer survive. Adopting Redis Streams now
is a deferral of that decision, not a commitment against it.

## Consequences

### Positive

- **Zero new infrastructure.** Redis is already in production; the team
  already operates it, monitors it, and backs it up. No new brokers, no new
  failure domain, no new budget line.
- **Fast time-to-value.** Producers switch from inline delivery to `XADD` and
  a small worker pool consumes with `XREADGROUP` — days of work, well under
  the 2-week constraint.
- **Decoupling fixes the incident class.** Notifications leave the request
  cycle, so 800ms–8s tail latency and webhook-induced connection-pool
  exhaustion disappear from user-facing requests. The web server can no
  longer be taken down by a slow external endpoint.
- **At-least-once delivery with retry, out of the box.** The PEL tracks
  delivered-but-unacknowledged entries; on a worker crash, `XAUTOCLAIM`
  reassigns them to a live consumer. Combined with exponential backoff and a
  max-attempt threshold, this eliminates silent drops.
- **Effective exactly-once for billing.** At-least-once delivery plus
  consumer-side dedupe by event ID (unique constraint in PostgreSQL) gives
  exactly-once *delivery effect* — the strongest guarantee achievable for
  external side effects, and the same mechanism Kafka would require.
- **Adequate headroom.** Even at 10x projected traffic we sit one to two
  orders of magnitude below single-node capacity.
- **Low cognitive load for a 6-person team.** Streams are a documented Redis
  data type, not a separate platform; the existing Redis expertise transfers
  directly.

### Negative

- **Memory-bound retention.** Stream history is held in Redis memory and
  trimmed with `MAXLEN`; it is not a durable, disk-backed log. Long-term
  replay of months of events is not available (we do not currently need it —
  billing state lives in PostgreSQL, the system of record — but the option is
  closed).
- **No native exactly-once.** The broker guarantees at-least-once only; the
  idempotency layer for billing events is ours to build and maintain. (Kafka
  would not have removed this work either, since the sinks are external.)
- **No native DLQ.** Dead-letter handling (a `dlq:` stream plus re-drive
  tooling) must be implemented by us, as it would be with Kafka.
- **Per-entity ordering requires design.** A consumer group distributes
  entries round-robin, so ordering guarantees are per-stream, not per-entity.
  If "task completed" must never overtake "task assigned" for the same task,
  events must be sharded by entity ID into per-entity streams (or routed
  through a single ordered consumer per channel). Kafka gives per-partition
  ordering for free via a partition key; here it is a small design cost we
  must consciously pay.
- **Single-node ceiling.** Streams scale vertically on one Redis instance;
  beyond that, Redis Cluster adds real operational complexity (resharding,
  multi-key constraints). At 10x projected traffic this is not a concern, but
  it is the long-term ceiling.
- **Streams share memory with sessions and rate limiting.** A runaway stream
  or unbounded `MAXLEN` could degrade other Redis consumers; capacity and
  trimming must be monitored and budgeted.

## Alternatives Considered

### Apache Kafka — rejected

Kafka is the technically more powerful system — disk-backed log retention with
replay, strict per-partition ordering, consumer-group rebalancing, and
transactional exactly-once — and it is the obvious choice for a platform whose
traffic, team, and budget are the inverse of ours. None of those advantages
apply here:

- **Throughput is irrelevant to the decision.** We are ~3 orders of magnitude
  below Kafka's design point even at 10x growth. Paying Kafka's operational
  cost for capacity we will never use is buying a racing engine for a
  commuter car.
- **Exactly-once does not transfer to our sinks.** Kafka's EOS covers
  Kafka-to-Kafka flows. Emails and webhooks are external side effects, so the
  consumer-side idempotency layer is mandatory regardless of broker choice.
  Kafka's signature guarantee does not touch our hardest requirement.
- **The operational cost is disqualifying for this team.** Six engineers, no
  infrastructure specialist, no Kafka experience, modest budget, and a
  2-week delivery constraint. Self-hosting Kafka (brokers, KRaft metadata,
  partitions, rebalances, JMX, disk management) is a standing operational
  burden the team cannot absorb; Confluent Cloud is explicitly unaffordable.
  Standing it up, learning it, and migrating onto it inside 2 weeks is not
  realistic.
- **Redis Streams already satisfies the requirements that matter** —
  at-least-once via consumer groups and the PEL, retry via redelivery,
  decoupling from the request cycle, and an adequate growth path — on
  infrastructure the team already operates.

Should traffic, retention, or replay requirements eventually exceed what a
single Redis node can serve, the migration path to Kafka preserves the worker
abstraction and idempotency layer; this decision defers rather than forecloses
that move.

Other brokers were not shortlisted: RabbitMQ adds a new service without adding
anything Redis Streams lacks here, and managed SQS/SNS trades one operations
problem for vendor lock-in and per-message costs that grow with the 10x
target, without improving the exactly-once story for external side effects.
