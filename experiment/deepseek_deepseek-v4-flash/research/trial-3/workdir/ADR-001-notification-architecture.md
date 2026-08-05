# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

## Status

Proposed

## Context

The notifications module sends emails and webhooks when tasks are updated, assigned,
or completed. Today it runs synchronously inside the Flask request cycle, which is
the root cause of four production problems:

1. **Request timeouts** — outbound email/webhook calls block the HTTP response.
   Average latency is 800ms with spikes to 8s during peak hours.
2. **Silent failures** — when an email provider or webhook endpoint is down, the
   notification is dropped with no retry and no dead-letter queue.
3. **Cascading failures** — twice this year a slow webhook endpoint exhausted the
   connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired",
   "payment failed") must be delivered effectively exactly-once; the current
   system offers none.

### Requirements

- Decouple notification sending from the HTTP request cycle (async processing).
- Support retry with exponential backoff and a dead-letter queue.
- At-least-once delivery for all notifications; exactly-once for billing events.
- Add real-time WebSocket push within two quarters.
- Handle 10x traffic growth without re-architecting.

### Constraints

- Engineering team of 6 (3 senior, 3 mid-level); no dedicated infrastructure
  engineer.
- Redis already runs in production (session storage, rate limiting); the team
  operates it today.
- No Kafka experience on the team.
- Must deliver value within 2 weeks of setup/migration work.
- Modest budget — managed Confluent Cloud at full scale is not affordable now.
- Exactly-once semantics for billing notifications.

Current scale: 85k MAU, ~2M tasks/month, ~500 req/s peak. At 10x growth that is
~5k req/s peak — a few thousand notification events per second at worst, not a
high-throughput streaming workload by industry standards.

## Decision

**Adopt Redis Streams as the notification backbone.** Producers enqueue
notification events with `XADD`; a small fixed pool of consumer workers reads
with `XREADGROUP`, processes, and `XACK`s. Retryable failures go to a retry
stream with an attempt counter and exponential backoff; exhausted events land in
a dead-letter stream. Billing events carry an `event_id` that consumers use as an
idempotency key against a `UNIQUE` constraint in PostgreSQL.

Target shape:

```
Flask app ──XADD──> streams: notifications.email
                     notifications.webhook
                     notifications.billing ──XREADGROUP──> worker pool (2–4)
                                                              │
                                                              ├─ success → XACK
                                                              ├─ retryable → XADD retry stream (backoff × N) → DLQ
                                                              └─ billing → upsert by event_id (UNIQUE) then XACK
```

This is a library-level change (`redis-py` supports the full Streams API) on
infrastructure we already run. Estimated time-to-value: a few days, well inside
the 2-week constraint.

### Justification against the requirements

- **Async decoupling, retries, DLQ** — native primitives. Consumer groups track a
  Pending Entries List (PEL) per consumer; `XACK` removes processed entries.
  Stalled work is reclaimed with `XAUTOCLAIM` (Redis 6.2+), which scans the PEL
  and atomically reassigns idle entries — this is the at-least-once machinery.
- **Exactly-once for billing** — the honest position is that *no* broker gives
  end-to-end exactly-once when consumers write to external sinks (email
  providers, webhooks, PostgreSQL). Kafka's transactional exactly-once (KIP-98)
  holds only within Kafka's own read-process-write cycle, not across an HTTP
  call to a payment email vendor. Both options therefore require the same
  idempotency work at the consumer; Redis Streams does not put us at a
  disadvantage here. Deduplication on `event_id` (unique index in Postgres,
  idempotent webhook headers) delivers the billing guarantee.
- **Ordering** — Streams preserve strict per-stream order via monotonic,
  time-sequenced entry IDs (`<ms>-<seq>`). Kafka orders only within a partition
  and would force the same partitioning decision (e.g., `task_id` as partition
  key) to get per-task ordering. No advantage either way at our scale.
- **Consumer groups** — `XREADGROUP` delivers each entry to exactly one consumer
  in a group, exactly the work-queue semantics we need. Kafka's automatic
  rebalancing is the one place it is operationally friendlier, but it is also a
  classic small-team footgun (rebalance storms, lag spikes); a fixed pool of 2–4
  workers with manual assignment and an `XAUTOCLAIM` sweep is simpler to reason
  about.
- **Throughput** — a single Redis node sustains on the order of 10^5 stream
  operations per second; our 10x target is ~5k req/s (tens of thousands of
  events/s worst case). We use well under 10% of one node. Kafka's millions-of-
  messages-per-second capability is capacity we would pay for but never use.
- **Retention** — the requirement is retry-for-minutes/hours plus a DLQ, not
  long-term replay or event sourcing. Streams trimmed with `MAXLEN` (and a
  `noeviction` maxmemory policy so streams are never evicted) fully cover this.
  Kafka's multi-day log retention is a differentiator we do not need.
- **Operational complexity** — this is the decisive constraint. Kafka 4.0
  removed ZooKeeper in favor of KRaft (March 2025), which simplifies Kafka, but
  it remains a distributed JVM cluster: brokers plus a controller quorum,
  partition/replication tuning, JMX monitoring, lag and rebalance management,
  disk sizing. Standing that up, keeping it healthy, and building the consumer
  on an unfamiliar API, with 6 people and no infra engineer, cannot credibly fit
  in 2 weeks. Redis Streams adds *no new system*: the node, clients, monitoring,
  and runbooks already exist.
- **Real-time WebSocket push (next 2 quarters)** — Redis is already the natural
  fan-out fabric: stream consumer groups for durable delivery plus Pub/Sub for
  live fan-out to a WebSocket gateway. Kafka would add a second system to solve
  the same problem.
- **Budget** — near-zero incremental cost: at most a larger Redis instance or a
  dedicated streams node. Confluent Cloud at scale is explicitly out of budget;
  self-managed Kafka on EC2 costs brokers and, more expensively, the team's
  attention.

## Consequences

### Positive

- **Fastest time-to-value**: no new infrastructure, no new language/runtime, no
  new ops surface. A working async pipeline lands in days, not weeks.
- **Team fit**: the only message-bus skill required is one the team already has
  (operating Redis). No dedicated infra engineer needed.
- **Adequate headroom**: comfortably absorbs 10x traffic on a single node; the
  "without re-architecting" requirement is met.
- **At-least-once out of the box**: consumer groups + PEL + `XAUTOCLAIM` give
  delivery tracking and crash recovery with modest code.
- **Ordering and fan-out**: strict per-stream ordering; multiple consumer groups
  enable email/webhook/WebSocket consumers independently.
- **Incremental cost ≈ 0**: reuses the existing Redis instance (or a modestly
  sized dedicated one).

### Negative

- **No native exactly-once**: a consumer that crashes between `XREADGROUP` and
  `XACK` causes redelivery. We must implement idempotent sinks for billing
  (`event_id` uniqueness in Postgres; idempotent webhook delivery headers).
  Note this is equally true under Kafka — the work is ours either way.
- **Manual consumer-group management**: no automatic rebalancing. Adding or
  removing workers requires deliberate assignment, and a dead worker's PEL grows
  until the `XAUTOCLAIM` sweep runs. Acceptable for a fixed worker pool; we own
  the sweep job and alerting on PEL depth.
- **Memory-bound retention**: streams live in memory (plus RDB/AOF persistence);
  long-term replay is not a use case we support. Requires `MAXLEN` trimming and
  a `noeviction`-style policy so memory pressure can never evict undelivered
  events.
- **Durability is a config choice**: to avoid losing acknowledged events on node
  loss we must enable AOF (fsync everysec as a minimum) and run a replica /
  managed HA (ElastiCache or Sentinel). Same class of work Kafka demands, but on
  a system we already run.
- **Single-node ceiling**: throughput and storage are bounded by one Redis
  instance. If we later exceed it (sustained 100k+ events/s, multi-region
  requirements, or event sourcing), we will migrate the producer/consumer
  boundary to Kafka — a planned escape hatch, not today's problem.
- **DLQ, retry scheduling, and dedup are our code**: the broker provides the
  queue, not the policy. This is true of Kafka as well, but the work is
  explicitly on our roadmap.

## Alternatives Considered

### Apache Kafka — rejected

- **Operational complexity (decisive)**: even KRaft-only Kafka 4.0 is a
  distributed cluster (brokers + controller, replication and partition tuning,
  JMX/lag monitoring, rebalance management) with no one on the team experienced
  in it and no infra engineer to own it. With 6 engineers and a 2-week
  time-box, the cluster itself would consume the entire migration budget before
  any consumer code was written.
- **Cost**: Confluent Cloud at full scale is out of budget; self-managed brokers
  add EC2 cost plus the ops burden above.
- **Skills gap**: a 2-week constraint cannot absorb both standing up Kafka *and*
  learning its consumer model. Redis Streams uses an API surface (commands,
  PEL/XACK semantics) adjacent to tooling already in production.
- **Differentiators not needed at this scale**: Kafka's advantages — millions of
  messages/sec, multi-day retention with replay, broker-native exactly-once
  (KIP-98, Kafka-to-Kafka only), automatic rebalancing — do not move our
  requirements. Our peak is ~5k req/s; our retention need is minutes-to-hours
  with a DLQ; and end-to-end exactly-once to email/webhook sinks requires
  consumer-side idempotency regardless of broker.

Kafka is the right migration target if the pipeline outgrows a single Redis node
(sustained 100k+ events/s), if long-term event replay becomes a product
requirement, or if notifications grow into a general event backbone used by
multiple services. The consumer contract we are building now (event with an ID,
at-least-once, idempotent sink) carries over unchanged, so that migration is
contained.

Other queues (SQS/SNS, Celery/RabbitMQ) were out of scope for this comparison;
they were not evaluated in depth because they lack the combined ordering +
consumer-group + persistence profile, but nothing in this decision depends on
their exclusion.
