# ADR-001: Notification Subsystem Message Broker

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users with ~2M tasks created per month and peak traffic of ~500 req/s. Notifications (emails and webhooks on task updates, assignments, completions) are currently processed **synchronously inside the HTTP request cycle**. This has caused four documented problems:

1. **Request timeouts** — notification dispatch blocks the response. Average latency is 800 ms, spiking to 8 s during peak hours.
2. **Silent failures** — when an email provider or webhook endpoint is down, the notification is dropped with no retry or dead-letter queue.
3. **Cascading failures** — two incidents this year where a slow webhook endpoint exhausted the PostgreSQL connection pool, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once; the current system provides no such guarantee.

### Scaling targets

- Decouple notifications from the HTTP request cycle (async processing).
- Support retry with exponential backoff.
- Guarantee at-least-once delivery for all notifications; exactly-once for billing events.
- Add real-time WebSocket push notifications within 2 quarters.
- Handle 10× traffic growth (≈5,000 req/s peak) without re-architecting.

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level). No dedicated infrastructure engineer.
- **Current stack**: Python/Flask monolith, PostgreSQL, Redis (already in production for sessions and rate limiting).
- **Kafka experience**: none on the team today.
- **Timeline**: must deliver value within 2 weeks of starting the migration.
- **Budget**: modest — managed Confluent Cloud at full scale is not affordable.
- **Exactly-once**: billing notifications must not be duplicated or lost.

### Options under consideration

| Property | Apache Kafka | Redis Streams |
|---|---|---|
| **Throughput** | Millions of messages/sec (partition-bounded scaling) | ~1 M messages/sec single-node; horizontal via cluster |
| **Ordering guarantees** | Per-partition strict ordering; cross-partition unordered | Per-stream strict ordering (append-only log) |
| **Message retention** | Configurable (hours to weeks); persistent commit log | Configurable via `MAXLEN` or time-based trimming; persists until trimmed or evicted |
| **Consumer groups** | Mature (group coordination, rebalancing, offset management built in) | Supported (`XREADGROUP`, `XPENDING`, `XACK`); functional but less mature than Kafka |
| **Exactly-once semantics** | Native support via idempotent producer + transactional writes (KIP-447) | No native EOS; requires application-level idempotency (deduplication table, idempotency keys) |
| **Operational complexity** | High: broker cluster, ZooKeeper or KRaft, partition management, monitoring, tuning | Low: single Redis instance or small cluster; team already operates Redis in production |
| **Setup time** | Weeks (cluster provisioning, topic design, team ramp-up) | Days (add stream commands to existing Redis deployment) |
| **Cost** | Self-managed: significant ops overhead; Managed (Confluent): exceeds current budget at scale | Minimal: Redis already budgeted and running |
| **WebSocket integration** | Requires separate fan-out layer (e.g., Kafka → WebSocket bridge) | Direct: Redis Pub/Sub fans out to WebSocket servers; Streams handle persistent processing |

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Kafka is the stronger technical choice at extreme scale, but the decision must be made in context. The constraints — 6-person team with no Kafka experience, a 2-week delivery window, an existing Redis deployment, and a modest budget — make Kafka's operational overhead unjustifiable for our current stage. Redis Streams provides sufficient throughput, ordering, and consumer-group semantics for our projected load (10× current peak is still well under a single Redis node's capacity), while keeping operational complexity within what the team can sustain.

### How exactly-once is achieved for billing notifications

Redis Streams does not provide native exactly-once semantics. We will implement application-level idempotency for billing events:

1. Each billing notification carries a client-generated **idempotency key** (e.g., `billing:{org_id}:{event_type}:{entity_id}:{version_hash}`).
2. The consumer writes the idempotency key to a **deduplication table in PostgreSQL** before processing. The table has a `UNIQUE` constraint on the key; duplicate inserts are rejected, preventing double processing.
3. On retry, the consumer checks the dedup table: if the key exists and is marked `delivered`, the message is acknowledged and skipped. If it exists but is not `delivered`, the consumer resumes processing.
4. This pattern — sometimes called the "transactional outbox with idempotency table" — provides exactly-once delivery semantics in practice, provided the dedup write and the business action share a database transaction.

This approach is battle-tested in systems like Stripe's payment processing and is standard practice when the message broker lacks native EOS.

### Migration path (first 2 weeks)

| Week | Milestone |
|------|-----------|
| 1 | Add notification worker process; refactor notification dispatch to `XADD` to a Redis Stream; implement consumer group with `XREADGROUP`; add PostgreSQL dedup table for billing events; deploy to production with feature flag routing only non-critical notifications through the new path. |
| 2 | Route all notifications (including billing) through Redis Streams; add exponential backoff retry via `XPENDING` / `XCLAIM`; add dead-letter stream for permanently failed messages; remove synchronous notification code from request path. |

## Consequences

### Pros

- **Fast time to value.** The team can ship the initial async pipeline in days, not weeks, because Redis is already running and the team is familiar with it.
- **Sufficient throughput for projected growth.** A single Redis node handles well over 50K ops/sec in practice. At 10× current peak (≈5,000 notification-producing req/s), we are orders of magnitude below ceiling. Horizontal scaling via Redis Cluster is available if needed later.
- **Lower operational cost.** No new infrastructure to provision, monitor, or hire for. Redis is already in the runbook.
- **Tighter feedback loop.** Workers co-exist with the application deployment; no separate cluster to manage or reason about.
- **WebSocket path is natural.** Redis Pub/Sub provides low-latency fan-out to WebSocket servers; Streams handle the persistent, at-least-once path. The two compose cleanly.
- **Exactly-once for billing is achievable.** The PostgreSQL dedup-table pattern is well-understood and gives us practical exactly-once delivery without broker-level transactions.

### Cons

- **No native exactly-once semantics.** We must build and maintain the dedup-table pattern. If the idempotency key design is wrong, billing duplicates are possible. This is a design surface that Kafka would eliminate — but it is bounded and auditable.
- **Consumer group maturity.** Redis Streams consumer groups work but are less battle-tested than Kafka's. Edge cases around consumer failure, `XCLAIM` races, and pending-entry cleanup require careful handling in the worker code. We will need to invest in integration tests covering these scenarios.
- **Message retention is less robust.** Redis Streams trim by count or time, but they are not designed for long-term event replay. If we need to reprocess weeks of notifications, we would need a separate archival mechanism (e.g., writing to S3 or a data lake). Kafka's persistent commit log makes this trivial. For our use case — where notifications are consumed within seconds and retries are bounded — this is acceptable.
- **Scaling ceiling is lower than Kafka's.** Redis Streams on a single node top out at roughly 1M messages/sec. Kafka's partitioned architecture scales to tens of millions. At our projected 10× growth (5,000 req/s peak, each producing a small number of notifications), we are well within Redis's envelope. If the business grows another 100× beyond that, we should revisit. This is a deliberate trade-off: optimize for the next 2–3 years, not the next 10.
- **Operational tooling is thinner.** Kafka has a rich ecosystem (Kafka Connect, Schema Registry, ksqlDB, Confluent Control Center). Redis Streams has fewer off-the-shelf tools for monitoring consumer lag, replay, and multi-topic topologies. We will need to build lightweight internal tooling (a small admin dashboard for stream lag and dead-letter inspection).

## Alternatives Considered

### Apache Kafka — why we rejected it (for now)

Kafka is the better message broker on pure technical merits: native exactly-once semantics, durable commit log, mature consumer groups, and effectively unbounded horizontal scalability. We rejected it for this phase because:

1. **No team expertise.** None of our 6 engineers has operated Kafka in production. The learning curve — topic/partition design, consumer group rebalancing, offset management, monitoring — would consume far more than the 2-week delivery window.
2. **Operational overhead without an infra team.** Even with KRaft (removing ZooKeeper), operating a Kafka cluster requires ongoing capacity planning, partition rebalancing, broker monitoring, and incident response. We do not have a dedicated infrastructure engineer, and adding this burden to the team risks the reliability of the existing system.
3. **Budget.** Managed Confluent Cloud at our projected throughput would cost hundreds of dollars per month at the Basic tier, scaling significantly as volume grows. Self-managed Kafka on EC2 trades money for engineering time we don't have.
4. **Premature optimization for our scale.** At 500 req/s peak and a 10× growth target, Redis Streams provides more than enough headroom. Kafka's architectural advantages — cross-datacenter replication, multi-tenant topic isolation, stream processing pipelines — solve problems we don't have yet.

**We explicitly leave the door open to migrating to Kafka in the future.** If the platform reaches a scale where Redis Streams' throughput or retention limitations become binding constraints, or if the team grows an infrastructure specialty, we would reassess. The current architecture — with its dedup-table pattern and stream-per-notification-type design — can be adapted to a Kafka producer/consumer model with bounded refactoring effort. This decision is *reversible*; a Kafka migration would be *irreversible* for a team this size.

### Other alternatives briefly considered

| Alternative | Why rejected |
|---|---|
| **RabbitMQ** | Strong retry/DLQ support, but adds a new operational dependency with no team experience. Does not natively support the fan-out model needed for WebSocket push. |
| **AWS SQS + SNS** | Fully managed, but couples us to AWS-specific APIs, complicates local development, and makes the WebSocket fan-out path more complex (SNS → Lambda → WebSocket server). Also does not solve exactly-once without additional idempotency infrastructure — same problem as Redis Streams, but with vendor lock-in. |
| **Database-queue pattern (PostgreSQL SKIP LOCKED)** | Simplest option, but polling-based. Does not support real-time fan-out for WebSocket without additional pub/sub infrastructure. Puts load on the primary database under high throughput. |