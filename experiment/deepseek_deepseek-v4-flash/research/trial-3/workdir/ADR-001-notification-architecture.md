# ADR-001: Notification Subsystem — Apache Kafka vs Redis Streams

## Status

Proposed

## Context

The notification module sends emails and webhooks on task update, assignment, and
completion, and today it does so **synchronously inside the HTTP request cycle**
(`system_context.md:16`). That coupling has produced four concrete failures:

1. **Request timeouts** — notifications block the response: 800 ms average
   latency, spikes to 8 s at peak (`system_context.md:22`).
2. **Silent failures** — a down email provider or webhook endpoint drops the
   notification permanently; there is no retry and no dead-letter queue
   (`system_context.md:23`).
3. **Cascading failures** — twice this year a slow webhook exhausted the
   PostgreSQL connection pool and took down unrelated features
   (`system_context.md:24`).
4. **No delivery guarantees** — billing-critical notifications ("trial
   expired", "payment failed") must be delivered exactly once, but the current
   system offers no guarantee at all (`system_context.md:25`).

### Scale

- 85,000 monthly active users; ~2M tasks/month; ~500 req/s peak (`system_context.md:6-8`).
- 10x traffic growth must be absorbed without re-architecting (`system_context.md:34`).

### Constraints

- Engineering team of **6** (3 senior, 3 mid), **no dedicated infrastructure
  engineer** (`system_context.md:38`).
- **Redis already runs in production** for session storage and rate limiting
  (`system_context.md:15,39`) — the team operates it today.
- **No Kafka experience on the team** (`system_context.md:40`).
- **≤ 2 weeks** of setup/migration before delivering value (`system_context.md:41`).
- **Modest budget** — managed Confluent Cloud at full scale is not affordable
  today (`system_context.md:42`).
- Billing notifications must maintain exactly-once semantics (`system_context.md:43`).
- WebSocket push notifications must ship within two quarters (`system_context.md:33`).

The decision is therefore not "which queue has the best ceiling?" — it is
"which queue gets async delivery, retry, dead-lettering, and delivery
guarantees into production fastest, at lowest ongoing operational cost, with a
team of six?"

## Decision

**Adopt Redis Streams** as the notification backbone, consumed by dedicated
Python worker processes, with at-least-once delivery and consumer-side
idempotency for exactly-once billing semantics.

### Justification

**1. It reuses infrastructure the team already operates — the decisive factor.**

The team of six already runs Redis in production for sessions and rate
limiting (`system_context.md:15`). Redis Streams is a data structure on that
existing server (`XADD`/`XREADGROUP`/`XACK`), not a new system: no new cluster,
no new failure modes, no new on-call surface. This is what makes the two-week
constraint (`system_context.md:41`) achievable — worker consumers can be
written in the same Python codebase within days. Kafka, by contrast, is a
distributed system the team has never operated (`system_context.md:40`) and
would consume the entire two-week budget in cluster bring-up before a single
notification is processed.

**2. Throughput is not the constraint, and Redis Streams clears it by orders of magnitude.**

The notification fan-out is small: ~2M tasks/month (`system_context.md:7`)
with a handful of notifications per task gives an average of a few messages per
second and a realistic peak in the low thousands per second. A single Redis
node sustains roughly 100k+ small-message stream operations per second — two
to three orders of magnitude of headroom at current load, and roughly one
order of magnitude of headroom even at the 10x target (`system_context.md:34`).
Kafka's million-messages-per-second horizontal scaling is a capability this
system does not need and would pay for in complexity.

**3. Delivery guarantees: at-least-once + idempotency is the honest way to "exactly once".**

No broker — Kafka included — can deliver **end-to-end** exactly-once to an
external side effect (an email provider, a webhook endpoint). Kafka's
exactly-once semantics (EOS/transactions) guarantee exactly-once *within
Kafka*; the external HTTP call is still outside the transaction. The only way
to satisfy "exactly once for billing" is **at-least-once delivery plus an
idempotent consumer**: a unique `notification_id` dedup key enforced by a
PostgreSQL unique constraint, so a duplicate delivery becomes a no-op.

Redis Streams provides the at-least-once half cleanly: `XACK` is an explicit
acknowledgement, and the Pending Entries List (PEL) retains unacknowledged
entries for redelivery via `XAUTOCLAIM`. That is the correct primitive. The
idempotency half (dedup table + unique constraint) must be written regardless
of broker choice, so choosing Redis Streams sacrifices nothing.

**4. Retry, backoff, and dead-lettering map directly onto existing primitives.**

- Retry with exponential backoff: a worker that fails leaves the entry in the
  PEL and re-claims it after a visibility timeout; the next delivery attempt
  increments a counter.
- Dead-letter queue: after N failed attempts, `XADD` the message to a
  `notifications:dlq` stream for manual inspection — the same pattern Kafka
  teams build with a dead-letter topic, minus the extra cluster.

**5. Ordering is preserved per stream, matching the requirement.**

Redis Streams preserves total order within a stream; partitioning by
`task_id` (one stream per shard, or key-hashed streams) preserves per-task
ordering, functionally equivalent to Kafka's per-partition ordering. For
notifications, per-task order ("assigned" before "completed") is what matters,
and it is achievable without Kafka's partition-count planning.

**6. It feeds the WebSocket roadmap directly.**

Real-time push within two quarters (`system_context.md:33`) can consume Redis
Streams (or Redis Pub/Sub) from the WebSocket gateway — Redis is already in
the stack. Kafka would require a second infrastructure investment purely to
serve this feature.

**7. The abstraction boundary keeps a future Kafka migration cheap.**

Workers consume from a small queue interface (read → ack → apply idempotency).
If 10x growth ever becomes 100x and single-node Redis is genuinely exceeded,
the consumer code is portable to Kafka with an adapter; the decoupling benefit
of the ADR is preserved either way.

## Consequences

### Positive

- **Fast time-to-value** — Redis Streams uses the existing Redis instance;
  workers land in days, well inside the two-week window.
- **No new infrastructure or vendor cost** — Redis is already budgeted; no
  managed-Kafka spend against a modest budget (`system_context.md:42`).
- **Operational simplicity for a team of six** — one queue system, already
  operated; no broker fleet, no Zookeeper/KRaft, no rebalancing incidents.
- **Sub-millisecond enqueue latency** — `XADD` is in-memory, eliminating the
  800 ms–8 s synchronous overhead from the request path.
- **At-least-once delivery with explicit acks** — silent failures
  (`system_context.md:23`) become retryable, and `XAUTOCLAIM` supports the
  backoff design.
- **Dead-lettering via a second stream** — failed messages are visible instead
  of dropped.
- **Load isolation** — notification workers decouple webhooks from the HTTP
  path, ending the connection-pool cascading failures (`system_context.md:24`).
- **WebSocket push reuses the same store.**

### Negative

- **Memory-bound retention** — streams live in RAM and are trimmed with
  `MAXLEN`/`MAXAGE`; Redis is not a long-term archive. Billing audit history
  belongs in PostgreSQL (where the dedup table already records every delivery),
  not in the stream.
- **No native DLQ** — dead-lettering is a convention (a second stream + a
  worker-side failure counter), not a platform feature. It must be built and
  documented.
- **Exactly-once is not free** — it requires the consumer-side idempotency
  table and unique constraint; the team must implement and test it. (Kafka
  would *not* remove this work either, despite its EOS branding.)
- **Single-node throughput ceiling and durability** — Redis is memory-first;
  durability relies on AOF (`appendfsync everysec`) plus a replica. A crash can
  lose up to a second of queued messages, acceptable for notifications (the
  idempotent consumer re-creates them from the task's current state) but not a
  system-of-record property.
- **Shared-instance contention** — streams share the Redis used for sessions
  and rate limiting; at high load, run the queue on a dedicated Redis instance
  (or at minimum a separate logical DB with its own `maxmemory` policy) to
  protect the request path.
- **Cross-consumer parallelism trades global ordering** — like Kafka's
  partitions, multiple consumers in a group interleave messages; strict global
  order requires one consumer or per-task sharding, which caps parallel
  throughput for a single task.

## Alternatives Considered

### Apache Kafka (rejected)

Kafka is the technically stronger system in the abstract — millions of
messages/sec, long on-disk retention with replay, per-partition ordering,
consumer groups with rebalancing, and exactly-once semantics (EOS) at the
broker level. It was rejected because every one of its advantages is either
not needed here or does not deliver what the constraints demand:

- **Operational complexity is disqualifying for this team.** Six people, no
  dedicated infrastructure engineer (`system_context.md:38`), no Kafka
  experience (`system_context.md:40`). Self-hosting Kafka means brokers,
  KRaft/Zookeeper, partition/replication sizing, rebalancing, consumer-lag
  monitoring, and disk sizing — a permanent operational tax on a team whose
  first priority is shipping the notification fix inside two weeks.
- **Budget excludes the managed escape hatch.** Confluent Cloud at full scale
  is explicitly unaffordable (`system_context.md:42`); MSK still carries
  meaningful cost and still demands Kafka expertise the team does not have.
- **Throughput is overkill.** The workload peaks in the low thousands of
  messages per second; Redis Streams clears the 10x target
  (`system_context.md:34`) with an order of magnitude to spare. Kafka's scale
  is bought, not needed.
- **EOS does not solve the billing requirement.** Kafka's exactly-once is
  within-Kafka; end-to-end exactly-once to an email/webhook provider still
  requires the same idempotent-consumer work Redis Streams needs
  (`system_context.md:43`). The decision-critical guarantee is broker-neutral.
- **Long retention is not a current need.** Notifications are consumed within
  seconds; the audit source of truth is PostgreSQL. Kafka's durable replay is a
  feature this system would pay to operate without using.
- **Two-week constraint fails.** Cluster bring-up, topic/partition design, and
  team ramp-up consume the entire window before the first notification is
  processed asynchronously.

*Revisit condition:* if notification volume grows past what a single Redis node
can carry, or a durable, replayable system-of-record event stream becomes a
requirement, revisit Kafka (ideally MSK once budget allows). The queue adapter
boundary in the worker code keeps that migration contained.
