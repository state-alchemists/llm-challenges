# ADR 001 — Notification Subsystem: Redis Streams over Apache Kafka

- **Status**: Proposed
- **Date**: 2026-06-23
- **Deciders**: Engineering team (6 — 3 senior, 3 mid-level)
- **Context tags**: notifications, messaging, reliability, performance

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, peak ~500 req/s) handles notification delivery — emails and webhooks on task updates, assignments, and completions — synchronously inside the HTTP request cycle. This has caused four documented problems:

1. **Request timeouts**: Notification sending blocks responses. Average latency 800ms, spikes to 8s at peak.
2. **Silent failures**: Downstream provider outages silently drop notifications. No retry, no dead-letter queue.
3. **Cascading failures**: Two incidents this year where slow webhook endpoints exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") require exactly-once delivery; the current system provides none.

We need to decouple notification production from delivery, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), support real-time WebSocket push within 2 quarters, and absorb 10× traffic growth (~5,000 req/s peak) without re-architecting.

Constraints that bound this decision:

- 6-person team, no dedicated infrastructure engineer.
- Redis already in production for sessions and rate limiting.
- Zero Kafka operational experience on the team.
- Must deliver value within 2 weeks of starting migration.
- Modest budget — managed Confluent Cloud at our scale is not affordable.
- Exactly-once semantics must be achievable for billing notifications.

## Decision

> We will use Redis Streams as the message backbone for the notification subsystem.

Redis Streams provides sufficient throughput, ordering, and consumer-group semantics for our current and projected scale, while requiring no new infrastructure — we already operate Redis in production. Exactly-once delivery for billing notifications will be achieved through a PostgreSQL-backed idempotency table (deduplication on notification ID), combining Redis Streams' at-least-once guarantees with application-level deduplication.

## Rationale

### Throughput and scaling

Redis Streams handles hundreds of thousands of messages per second per instance. Our current peak (~500 req/s, projected 10× = ~5,000 req/s) is two orders of magnitude below Redis's capacity. Kafka's throughput advantage (millions of msg/s) is real but irrelevant at our scale — we would pay its operational cost for headroom we do not need.

### Ordering guarantees

Redis Streams guarantee per-stream ordering (strict FIFO within a single stream). Kafka guarantees per-partition ordering only. For our use case — a `notifications` stream consumed by worker processes — Redis's per-stream ordering is actually stronger than Kafka's per-partition model, which would require careful partition-key design to preserve order for related events.

### Consumer groups

Redis Streams' `XREADGROUP` provides consumer-group semantics (partitioned consumption, pending-entry lists for claim/redelivery). It lacks Kafka's mature rebalancing protocol and topic-level consumer-group isolation, but our topology is simple: one stream, one consumer group, N workers. We do not need multi-topic fan-out or complex routing that would justify Kafka's consumer-group protocol.

### Exactly-once semantics

Kafka offers transactional exactly-once delivery via its Transactions API (idempotent producer + transactional consumer). Redis Streams provides at-least-once delivery natively. We achieve exactly-once for billing notifications by writing a deduplication key (notification ID) to PostgreSQL before dispatching the notification action. If a message is redelivered (which Redis Streams' `XPENDING` + `XCLAIM` mechanism supports), the worker checks the dedup table and skips already-processed IDs. This is the same pattern used by Stripe, Shopify, and other systems that need exactly-once over at-least-once transports, and it composes with our existing PostgreSQL — no new infrastructure required.

### Message retention

Kafka's durable, configurable log retention (days to weeks) is superior for event-sourcing and replay scenarios. Our notification stream is a work queue, not an audit log — once a notification is delivered, we do not need to replay the stream. Redis Streams' `MAXLEN` trimming and time-based eviction are sufficient. The authoritative record of what happened lives in PostgreSQL (task history, billing ledger), not in the message broker.

### Operational complexity

This is the decisive constraint. We already operate Redis. We have zero Kafka experience and no dedicated infrastructure engineer. A Kafka deployment (even KRaft mode without ZooKeeper) introduces: broker provisioning, partition management, replication factor tuning, monitoring (under-replicated partitions, ISR shrinkage), and capacity planning for disk and network. This knowledge gap would push setup well beyond the 2-week delivery constraint. Redis Streams adds a new data structure to an existing service — the operational delta is monitoring stream length and consumer-group lag.

### Cost

Self-hosted Kafka requires 3+ brokers for replication tolerance. Managed Confluent Cloud is priced per partition-hour and throughput — at our scale, it exceeds our budget. Redis is already paid for and running.

## Alternatives Considered

- **Apache Kafka** — Rejected. Kafka is the stronger choice at higher scale (millions of msg/s, multi-tenant event streaming, long retention, complex consumer topologies) and for teams with Kafka expertise. It loses here on three binding constraints: (1) 2-week delivery window — our team would need weeks just to build operational fluency; (2) operational overhead — no dedicated infra engineer to own broker health; (3) budget — managed Kafka is unaffordable at our scale, and self-hosting requires 3+ brokers we cannot staff. We would reconsider Kafka if throughput requirements exceed ~100k msg/s, if we need multi-datacenter replication, or if the team grows to include dedicated platform engineering.

- **PostgreSQL LISTEN/NOTIFY + queue tables** — Rejected. Using a PostgreSQL table as a queue (e.g., `SELECT ... FOR UPDATE SKIP LOCKED`) with `LISTEN/NOTIFY` for wake-up avoids new infrastructure entirely. However, polling-based dequeue at 5,000 req/s creates write amplification on the primary, competing with the application's OLTP workload. PostgreSQL also lacks native consumer-group partitioning, requiring application-level claim logic. This option becomes attractive only at lower throughput (<500 msg/s) or when adding any new data store is truly impossible.

## Consequences

- **Positive**
  - No new infrastructure to provision, monitor, or staff. Redis is already in our stack.
  - Setup measured in days, not weeks — a single worker process reading `XREADGROUP` against a `notifications` stream can ship in the first sprint.
  - At-least-once delivery with `XPENDING`/`XCLAIM` redelivery eliminates silent failures and supports exponential backoff (workers set `XPENDING` idle time thresholds before claiming).
  - Exactly-once for billing notifications via PostgreSQL dedup table — a proven, auditable pattern.
  - Per-stream FIFO ordering is simpler to reason about than Kafka's per-partition model for our single-stream topology.
  - Natural path to WebSocket push: workers can publish to Redis Pub/Sub channels that WebSocket servers subscribe to, staying within the same infrastructure.

- **Negative**
  - Redis Streams is not a durable log. If Redis is not configured with `appendonly yes` and a replication replica, a node failure before `XADD` propagation loses messages. Mitigation: enable AOF persistence and configure a Redis replica for the streams logical database.
  - Consumer-group rebalancing in Redis Streams is less sophisticated than Kafka's. Workers must handle `XCLAIM` logic for failed consumers explicitly. At our scale (N ≈ 4–8 workers), this is manageable, but it does not auto-rebalance on topology changes the way Kafka does.
  - No native multi-topic routing. If we later need separate streams for emails, webhooks, WebSocket push, and billing events, we manage stream names and consumer groups ourselves. Kafka's topic model is more ergonomic for this — we accept the added application complexity in exchange for simpler infrastructure.
  - Redis Streams' maximum practical stream length is bounded by memory. With `MAXLEN ~100000` trimming and prompt consumption, this is not a problem at our throughput, but it means Redis Streams cannot serve as a long-term event archive. The source of truth remains PostgreSQL.

- **Follow-ups**
  1. Enable AOF persistence and configure a Redis replica for the streams database before production traffic.
  2. Implement the notification worker service: `XREADGROUP` consumer, exponential backoff on failure, `XCLAIM` for redelivery of stale pending entries.
  3. Add the PostgreSQL dedup table for billing notifications (idempotency key = notification ID).
  4. Integrate WebSocket push: worker publishes to Redis Pub/Sub channel; WebSocket servers subscribe and relay to connected clients.
  5. Add monitoring: stream length, consumer-group lag (`XPENDING` count), worker processing latency.
  6. Re-evaluate Kafka if throughput exceeds 100k msg/s, if we need multi-datacenter replication, or if the team grows to include dedicated platform engineering.