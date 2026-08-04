# ADR-001: Use Redis Streams for the Notification Subsystem

## Status

Accepted (2026-08-04). Revisit when any trigger condition in "Alternatives Considered" is met.

## Context

We run a SaaS project management platform (85k MAU, ~2M tasks/month, ~500 req/s peak) on a Python/Flask monolith, PostgreSQL, and four web servers behind nginx on AWS. Notifications (email, webhooks) are currently sent synchronously inside the HTTP request cycle, which causes:

1. **Request timeouts** — notification dispatch blocks the response: 800ms average latency, spikes to 8s at peak.
2. **Silent failures** — a down email provider or webhook endpoint drops the notification with no retry and no dead-letter queue.
3. **Cascading failures** — two incidents this year where a slow webhook exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") require exactly-once delivery; the current system guarantees nothing.

The target state: decouple dispatch from the request cycle, retry with exponential backoff, at-least-once delivery for billing events with exactly-once where feasible, real-time WebSocket push within two quarters, and 10x traffic growth without re-architecting.

Constraints:

- Engineering team: 6 people (3 senior, 3 mid-level), **no dedicated infrastructure engineer**.
- Redis is already in production (session storage, rate limiting).
- **No Kafka experience on the team.**
- No more than **2 weeks** of setup/migration before delivering value.
- Modest budget — managed Confluent Cloud is explicitly out of scope.
- Billing notifications must maintain exactly-once semantics.

**Workload math** (estimates, assumptions labeled): 2M tasks/month ≈ 67k tasks/day ≈ 2/s average during business hours; at 1–3 notifications per task that is roughly 2–6 msg/s average. At peak, taking an aggressive bound — every one of the 500 req/s generating 3 notifications — gives ~1,500 msg/s; a realistic fraction (10–30% of requests) gives ~50–450 msg/s. At 10x growth the realistic peak is ~0.5–4.5k msg/s, worst case ~15k msg/s.

## Decision

**Use Redis Streams, on a dedicated Redis instance, as the notification backbone.** Do not co-locate with the session/rate-limit cache: a separate node isolates a growing, latency-sensitive streaming workload from cache eviction policy and memory pressure.

Concretely:

- **Producers** (Flask request handlers) append small events to channel streams (`notifications:email`, `notifications:webhook`, later `notifications:ws`) after the DB transaction commits. Events carry `event_id`, `event_type`, and entity references — not rendered content; consumers hydrate from PostgreSQL.
- **Billing-critical events** additionally go through a PostgreSQL outbox table written in the same transaction as the business change, with a relay that publishes to Redis. This makes the event durable in the source of truth even if Redis loses data, and it is the mechanism that actually upholds the billing guarantee.
- **Consumers** read with `XREADGROUP` consumer groups — one group per channel, a handful of consumers per group. The group's Pending Entries List (PEL) is the retry ledger: failed deliveries are simply not acknowledged, and `XAUTOCLAIM` (Redis ≥ 6.2, redis.io/docs/latest/commands/xautoclaim) with increasing `MIN-IDLE-TIME` implements exponential backoff by reclaiming entries only after their backoff window. After N attempts, entries move to a `notifications:dlq` stream for inspection and manual replay.
- **Exactly-once for billing** is achieved at the application layer: at-least-once delivery from the stream, plus an idempotency table in PostgreSQL (`notification_deliveries(event_id PRIMARY KEY, status, ...)`) and idempotency keys on provider APIs where available. This yields effectively-once delivery. This is not a compromise — it is the only honest way to satisfy the requirement, and it works identically on Kafka (see below).
- **WebSocket push** (2-quarter target) is served from the same pipeline: a `notifications:ws` stream consumed by the WebSocket gateway, or Redis Pub/Sub for the ephemeral fan-out where replay is not needed.
- **Capacity headroom**: published single-node benchmarks put `XADD` ingestion around 1.4×10⁵ ops/s (ARM reference benchmark, learn.arm.com/learning-paths/servers-and-cloud-computing/redis-cobalt/redis-benchmark-and-validation/) and ~2.5×10⁵ ops/s pipelined on modest hardware. Our worst-case 10x peak (~15k msg/s) sits roughly an order of magnitude below single-node capacity; the realistic 10x peak is two orders of magnitude below. The stated "10x without re-architecting" requirement is met with margin.

**Why Redis Streams wins here**: the decision is driven by the constraints, not by feature checklists. The workload is small (hundreds of messages per second, even at 10x); the team is small with no infrastructure engineer and no Kafka experience; Redis is already an operated component; the budget rules out managed Kafka; and the one requirement that sounds like it favors Kafka — exactly-once — is an application-layer property that Kafka does not actually provide for external side effects either.

**Migration plan (fits the 2-week constraint):**

- Week 1: provision the dedicated Redis node (AOF `everysec`, a replica, Multi-AZ if on ElastiCache); create the streams and groups; add the producer `XADD` calls and the outbox relay for billing; stand up email/webhook consumers with the PEL/`XAUTOCLAIM`/DLQ loop; add the idempotency table.
- Week 2: ramp traffic 10% → 100% with the synchronous path as a fallback, then delete the synchronous dispatch; wire monitoring — stream length, PEL depth per group, DLQ count, consumer lag (`XINFO STREAM` / `XINFO GROUPS`) — with alerts on PEL growth.

## Consequences

### Positive

- **Fast, low-risk delivery**: days of work, not weeks; no new infrastructure paradigm; the team already operates Redis. The 2-week constraint is met comfortably.
- **Cost**: one small dedicated node (a fraction of a 3-broker MSK minimum footprint); Confluent Cloud excluded by budget anyway.
- **Throughput headroom**: 1–2 orders of magnitude above the 10x target on a single node, based on published `XADD` benchmarks (see Decision).
- **Retry/DLQ semantics come built-in**: the PEL plus `XAUTOCLAIM` is precisely the retry-with-backoff/dead-letter pattern the requirements call for, without building retry machinery on top of a general-purpose log.
- **Small operational surface**: streams, groups, consumers, and the PEL are learnable in days; no partition/rebalance/offset model to internalize, no broker fleet to size or tune.
- **Strict per-stream ordering**: `XADD` preserves insertion order; adequate for notification semantics, which are independent side effects.
- **Clean future migration path**: the producer/consumer shape (publish → consume from a group) is identical to Kafka's, so if the revisit triggers fire, swapping the transport is a contained adapter change rather than a re-architecture.

### Negative

- **Memory-bound retention**: streams live in RAM; long-term replay is limited by `MAXLEN`/`MAXAGE` trimming and memory cost, whereas Kafka's disk log retains and replays for weeks cheaply. *Mitigation*: retain hours–days in Redis; archive consumed events to PostgreSQL/S3 for audit; billing events are already durable in the outbox.
- **Weaker durability than Kafka**: Redis is memory-first; with AOF `everysec` a node failure can lose up to ~1s of un-acked entries, and a bare Redis without persistence can lose everything. Kafka persists to disk by design. *Mitigation*: AOF `everysec` + replica + Multi-AZ; the billing path's outbox means the event survives Redis loss and the relay re-publishes, so the guarantee is not compromised.
- **Single-node scaling ceiling**: horizontal scaling via Redis Cluster sharding is more manual than Kafka partitions. *Mitigation*: headroom is 1–2 orders of magnitude beyond the 10x target; the revisit triggers define when to move.
- **Per-key ordering is less natural**: Kafka orders by partition key; Redis distributes entries across consumers in a group, so strict ordering holds per stream, not per entity. *Mitigation*: acceptable for independent email/webhook side effects; where ordering matters (e.g., sequential billing notices), use a dedicated stream or sequence at the consumer.
- **Manual consumer management**: unlike Kafka's rebalancing, Redis consumers are added/removed explicitly, and a permanently dead consumer leaves entries in the PEL. *Mitigation*: fixed consumer names, small consumer counts, `XAUTOCLAIM` reclaims stalled work, and PEL-depth alerts catch anomalies.
- **Exactly-once is not broker-provided**: Redis Streams delivers at-least-once; exactly-once must be built with the idempotency table. This is identical to the Kafka situation for external side effects (see below), so it is a cost of the design, not a differentiator lost.

## Alternatives Considered

### Apache Kafka (self-hosted) — Rejected

- **Operational complexity**: Kafka 4.0 (March 2025) removed ZooKeeper in favor of KRaft (kafka.apache.org/blog/2025/03/18/apache-kafka-4.0.0-release-announcement/), but you still run and tune a broker fleet: controllers, partition counts, replication and retention settings, disk throughput planning (Kafka is log-append I/O heavy), consumer rebalancing behavior, and lag/offset monitoring. With zero Kafka experience on a 6-person team and no dedicated infra engineer, a correct setup plus migration is realistically well beyond the 2-week constraint.
- **Throughput is irrelevant at this scale**: Kafka's partitioned scale targets workloads 3+ orders of magnitude above ours, even at 10x growth. We would pay for capacity and complexity we cannot use.
- **Exactly-once does not differentiate**: Kafka's transactions and idempotent producers guarantee exactly-once *within the Kafka pipeline only* — "there is no support for transactions that include external systems" (developer.confluent.io/courses/architecture/transactions/). An email send or webhook POST is an external, non-transactional side effect; the duplicate-send problem Kafka's EOS cannot solve is exactly the one we must solve. Both options therefore require the same consumer-side idempotency; Kafka merely adds a more complex way to get to the same place.
- **Skill cost**: partitions, offsets, rebalancing, retention, compaction is a real onboarding lift for six engineers who would rather be shipping features.
- **Verdict**: the right tool at ~100x our volume; the wrong tool for this team, timeline, and budget.

### Managed Kafka (MSK / Confluent Cloud) — Rejected

- Confluent Cloud is explicitly excluded by the budget constraint.
- MSK removes some broker operations but still requires partition/retention/IAM/tuning decisions, carries a minimum 3-broker footprint, and costs an order of magnitude more than a dedicated Redis node — without removing the team's Kafka learning curve.

### AWS SQS / SNS — Not selected

- A fully managed, dead-simple alternative with DLQs built in, and worth a look on its own merits. Not selected because it adds a new service and delivery paradigm, does not reuse the Redis operations the team already runs, offers no consumer-group-style replay, and serves the WebSocket push path less naturally than streams. Redis Streams wins on reuse and one less moving part.

### Status quo (synchronous dispatch) — Rejected

- Synchronous dispatch is the incident source: timeouts, silent drops, and pool exhaustion. The requirement to decouple from the request cycle is non-negotiable.

**Revisit triggers** — adopt Kafka when any of these holds: sustained notification volume above ~50k msg/s (≈100x today's peak); a requirement for event sourcing or analytics replay over months of history; multi-region active-active with cross-region replication; or the team gains the infra expertise and Kafka skills to operate it. Until then, Redis Streams is the correct, lowest-risk choice given the constraints.
