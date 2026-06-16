# ADR 001 — Notification Subsystem Message Broker

- **Status**: Proposed
- **Date**: 2026-06-15
- **Deciders**: Backend engineering team, Engineering Manager
- **Context tags**: notifications, messaging, scaling, kafka, redis

## Context

Our SaaS project management platform serves 85,000 monthly active users with ~2M tasks created per month and a peak of ~500 req/s during business hours. Notifications (emails, webhooks) are currently processed synchronously inside the HTTP request cycle on a Python/Flask monolith. This has caused three categories of failure:

1. **Request timeouts** — average notification latency is 800 ms with spikes to 8 s, blocking response completion.
2. **Silent data loss** — no retry or dead-letter mechanism; a downed email provider or webhook endpoint silently drops notifications.
3. **Cascading outages** — two incidents this year where a slow webhook consumer exhausted the connection pool, taking down unrelated features.

We must decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery for billing events (exactly-once where feasible), and prepare for real-time WebSocket push within two quarters. The system must handle a 10× traffic increase (~5,000 req/s peak) without re-architecting.

**Hard constraints**:

- Engineering team: 6 people (3 senior, 3 mid-level). No dedicated infrastructure engineer.
- Redis is already running in production (session storage, rate limiting). No team member has Kafka operational experience.
- Setup and initial migration must deliver value within 2 weeks.
- Budget is modest; managed Confluent Cloud at full production scale is not affordable today.
- Exactly-once delivery semantics for billing-critical notifications.

## Decision

We will use **Redis Streams** as the message broker for the notification subsystem.

Redis Streams meets all functional requirements — ordered consumer groups, persistent message history, acknowledged delivery, and replay — while fitting within the team's current operational capacity and the 2-week delivery window. Kafka's strengths (massive throughput ceiling, multi-tenant log compaction, Kafka-based exactly-once transactions) are real but not required at our scale, and its operational overhead would violate the team-size and time constraints.

## Rationale

### Throughput

- **Current peak**: ~500 req/s. **10× target**: ~5,000 req/s.
- Redis Streams handles well over 100,000 msgs/s on a single node (pipeline-friendly `XADD`/`XREADGROUP` calls). Our 5,000 req/s target is two orders of magnitude below Redis's ceiling.
- Kafka's throughput advantage (millions of msgs/s across partitions) is not relevant at our scale.

### Ordering Guarantees

- Redis Streams guarantee per-consumer-group ordering within a single stream. Our notification topology uses one logical stream per event category (`notifications:billing`, `notifications:webhook`, `notifications:email`), so per-stream ordering is sufficient.
- Kafka provides per-partition ordering. We would need the same partition-per-category discipline, so no real advantage here.

### Message Retention

- Redis Streams support configurable `MAXLEN` or time-based trimming. We will set `MAXLEN ~1,000,000` per stream (roughly 2 weeks of retention at 10× traffic) and rely on PostgreSQL as the long-term audit store for billing events.
- Kafka's long-term retention and log compaction are superior, but we don't need a replayable event-sourcing log — we need a work queue with bounded retention and a durable audit trail in Postgres.

### Consumer Groups

- Redis 5.0+ supports consumer groups natively via `XREADGROUP`, `XACK`, and `XPENDING`. This gives us the same fan-out, claim, and redelivery semantics we need for multiple notification workers.
- Kafka consumer groups are more mature (rebalancing protocol, cooperative sticky assignor), but our consumer topology is simple and static (a fixed pool of worker processes). Kafka's rebalancing sophistication adds complexity we don't benefit from.

### Exactly-Once Semantics

- **Billing notifications**: We implement exactly-once at the application layer using an idempotency key (a deterministic hash of `{tenant_id, event_type, entity_id, timestamp_bucket}`) stored in PostgreSQL. The worker checks this key before processing; duplicate deliveries from Redis (at-least-once) become no-ops. This is the same pattern Stripe uses for webhook idempotency and satisfies the requirement without relying on Kafka's transactional producer/consumer, which requires significant configuration (transactional IDs, isolation levels, `read_committed` consumer) and is easy to misconfigure.
- **Non-billing notifications**: At-least-once is acceptable. Redelivering a "task completed" email is a minor nuisance, not a billing error.

### Operational Complexity

- **Redis**: Already in production. Team has operational runbooks, alerting, and memory management experience. Adding Streams means learning three new commands (`XADD`, `XREADGROUP`, `XACK`) and one new monitoring dimension (stream length). No new infrastructure to provision, secure, or backup.
- **Kafka**: New infrastructure. Requires broker nodes (minimum 3 for production), ZooKeeper or KRaft quorum, topic configuration, partition planning, JVM tuning, disk I/O management, and 24/7 monitoring for a system no one on the team has operated. Managed Confluent Cloud removes the ops burden but exceeds our budget at production throughput.

### Time to Value

- Redis Streams: Functional producer/consumer within 2–3 days against the existing Redis instance. Full migration (swap synchronous sends for `XADD`, add worker processes with `XREADGROUP`, idempotency table in Postgres) in ~10 days.
- Kafka: 1–2 weeks for infrastructure provisioning, security hardening, and team training before any application code ships. This misses the 2-week value deadline.

### Future Path to WebSocket Push

- WebSocket fan-out reads from the same Redis Streams via a dedicated consumer group. This is a natural extension of the worker model — a `ws-pusher` group reads `notifications:*` streams and pushes to connected sockets.
- If we later outgrow Redis (e.g., multi-datacenter replication, event-sourcing requirements), we can introduce Kafka as a second tier with Redis as a local buffer. This is a well-documented pattern (Redis → Kafka sidecar). Choosing Redis now does not foreclose Kafka later; choosing Kafka now commits us to its operational cost immediately.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming. It offers superior long-term retention via log compaction, multi-consumer replay from arbitrary offsets, and true exactly-once delivery through transactional producers and idempotent consumers.

**Why rejected**: The operational cost is disproportionate to our current needs. At ~5,000 req/s peak, Kafka's throughput ceiling is 200× what we require. Its operational surface (broker clusters, partition management, JVM tuning, rebalancing protocols) demands dedicated infrastructure expertise the team does not have. Managed Kafka (Confluent Cloud) eliminates the ops burden but exceeds our budget at production data rates. The 2-week delivery deadline cannot accommodate the infrastructure provisioning, security configuration, and team ramp-up Kafka requires.

**When Kafka would win**: If our traffic grew beyond 50,000 req/s, if we needed multi-region event replication, or if we adopted an event-sourcing model requiring indefinite log retention and cross-team replay, Kafka's strengths would justify its cost. At that point we would revisit this decision and consider introducing Kafka as a second tier alongside Redis.

### PostgreSQL LISTEN/NOTIFY + queue tables

Using PostgreSQL as both the durable store and the notification channel (via `NOTIFY`/`LISTEN` or a polled queue table) would avoid introducing any new infrastructure.

**Why rejected**: `NOTIFY`/`LISTEN` is fire-and-forget — no persistence, no consumer groups, no replay. Polled queue tables solve persistence but add read/write load to the already-single-primary Postgres instance, and polling latency is unsuitable for real-time WebSocket push. This option also fails the decoupling requirement: we would be trading synchronous HTTP-blocked notifications for synchronous DB-polled notifications, adding load to the database we are trying to protect from cascading failures.

## Consequences

### Positive

- **Immediate value**: Decouples notifications from the HTTP request cycle within days, not weeks. Unblocks the latency and cascading-failure fixes the team needs now.
- **Minimal operational surface**: No new infrastructure to provision, monitor, or upgrade. Redis Streams reuse the existing Redis instance the team already operates.
- **Idempotent exactly-once for billing**: Application-layer idempotency keys in Postgres provide the delivery guarantee we need without Kafka's transactional producer complexity.
- **WebSocket-ready**: Adding a `ws-pusher` consumer group is a straightforward extension of the same stream model, delivering real-time push within the 2-quarter timeline.
- **Reversible**: If traffic or requirements eventually justify Kafka, we can introduce it as an upstream tier without rewriting the worker logic (same consumer-group abstraction, different broker implementation).

### Negative

- **Redis is not a durable log**: If the Redis node loses data before consumers acknowledge (e.g., `appendonly yes` not configured, or a disk failure between fsyncs), unacknowledged messages can be lost. We mitigate this with Redis persistence (`appendonly yes`, `fsync everysec`) and by writing billing events to Postgres before `XADD`. The blast radius of a single-node Redis failure is bounded by the fsync interval (~1 s), which is acceptable for non-billing notifications and fully covered by Postgres-backed idempotency for billing.
- **Single-node Redis is a SPOF**: Our current Redis deployment is not clustered. If it goes down, notification processing pauses until recovery. This mirrors our current session-store risk (Redis is already a SPOF for sessions), and is strictly better than the status quo where a Redis outage would also break the web tier. We should plan Redis Sentinel or Redis Cluster as a follow-up, but this is not a blocker for the initial migration.
- **No native multi-datacenter replication**: Redis Streams do not replicate across regions. If we expand to multi-region deployment, we will need to revisit this choice or add a Kafka tier.
- **Stream memory management**: Unbounded streams consume memory. We must enforce `MAXLEN` trimming and monitor stream length. This is a new operational task, but it is a single metric on an existing system.

### Follow-ups

1. Enable Redis `appendonly yes` with `fsync everysec` before cutting over notification traffic.
2. Create the `notification_idempotency` table in Postgres with a unique constraint on `{tenant_id, event_type, entity_id, timestamp_bucket}`.
3. Add `stream_length` and `pending_entries_count` metrics to the existing Redis monitoring dashboard.
4. Implement the worker pool: `XREADGROUP`-based consumers for `notifications:billing`, `notifications:email`, and `notifications:webhook` with exponential backoff retry and `XCLAIM`-based redelivery for stuck messages.
5. Add the `ws-pusher` consumer group for WebSocket delivery (Q2 target).
6. Evaluate Redis Sentinel or Redis Cluster for HA before the 10× traffic milestone (Q3–Q4).
7. Revisit this ADR if sustained peak exceeds 20,000 req/s, multi-region replication is required, or the team grows an infrastructure specialty.