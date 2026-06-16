# ADR 001 — Notification Subsystem Message Broker

- **Status**: Proposed
- **Date**: 2026-06-16
- **Deciders**: Engineering team (6 engineers)
- **Context tags**: notifications, messaging, scaling, redis, kafka

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, peak ~500 req/s) handles all notifications — emails, webhooks, and soon WebSocket pushes — synchronously inside the HTTP request cycle. This architecture has produced four concrete failures:

1. **Request timeouts** — notification delivery blocks the response (800ms average, 8s spikes at peak).
2. **Silent data loss** — downstream outages drop notifications with no retry or dead-letter queue.
3. **Cascading failures** — two incidents this year where slow webhook endpoints exhausted the PostgreSQL connection pool, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once; the current system provides no such guarantee.

We need to decouple notification production from delivery, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible for billing), support WebSocket push within two quarters, and absorb 10× traffic growth without re-architecting.

Hard constraints:
- 6-person team (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already runs in production for sessions and rate limiting.
- No Kafka experience on the team.
- Delivery must begin producing value within 2 weeks of starting.
- Budget does not cover managed Confluent Cloud at our scale.

## Decision

We will use Redis Streams as the message broker for the notification subsystem.

Redis Streams provides ordered, consumer-group-based message consumption on infrastructure the team already operates. Notification producers (Flask request handlers) write to Redis Streams via `XADD`; worker processes consume via `XREADGROUP`, apply exponential-backoff retries on failure, and acknowledge with `XACK`. Exactly-once semantics for billing notifications are achieved through application-level idempotency keys stored in PostgreSQL — the same pattern both Kafka and Redis Streams require for true end-to-end exactly-once delivery.

## Rationale

### Throughput

Current peak is ~500 req/s; the 10× growth target is ~5,000 req/s. Redis Streams handles tens of thousands of messages per second on a single instance. Our notification volume (a subset of requests) is well within that ceiling. Kafka's superior throughput at the million-message-per-second range is capacity we do not need and will not need at 10× scale.

### Ordering Guarantees

Redis Streams provide strict per-stream insertion ordering via monotonic IDs (`milliseconds-sequence`). This is sufficient for our use case, where ordering matters within a notification type (e.g., "task assigned" before "task completed" for the same task) and is achieved by routing related events to the same stream. Kafka provides per-partition ordering, which is equivalent in practice but requires explicit partition key management.

### Message Retention

Redis Streams support `MAXLEN` trimming and time-based eviction (`MINID`). Our use case demands retention only until consumers acknowledge — typically seconds to minutes. We will set `MAXLEN ~100000` as a safety cap; acknowledged messages are pruned. Kafka's configurable, disk-backed retention to days or weeks is unnecessary for a notification dispatch queue where messages are consumed within seconds.

### Consumer Groups

`XREADGROUP` + `XACK` + `XPENDING` provide functional consumer group semantics: partitioned delivery, pending-entry tracking for crash recovery, and claim/transfer for stuck messages. This covers our retry and dead-letter requirements. Kafka's consumer groups are more mature (automatic rebalancing, session timeouts), but our scale — likely 2–4 worker processes — makes manual or semi-automated rebalancing entirely tractable.

### Exactly-Once Semantics

Neither Kafka nor Redis Streams deliver end-to-end exactly-once semantics on their own. Kafka's transactional producer/consumer provides exactly-once within the Kafka cluster itself, but the moment a consumer performs a side effect (sending an email, calling a webhook), duplicates become possible on retry. The standard solution in both systems is application-level idempotency: assign each notification a deterministic ID, check against a delivered-set in PostgreSQL before executing the side effect, and deduplicate on retry. Redis Streams with idempotent handlers achieves the same guarantee with less infrastructure.

### Operational Complexity

This is the decisive factor. Kafka introduces a new distributed system: broker cluster (3+ nodes for production), KRaft/ZooKeeper quorum, topic/partition configuration, monitoring, capacity planning, and failure recovery. Our team has no Kafka operational experience and no dedicated infrastructure engineer. Self-hosted Kafka would demand weeks of learning, staging, and hardening before it could safely carry billing-critical traffic. Managed Confluent Cloud would offload operations but exceeds our budget at scale.

Redis Streams run on the Redis instance we already operate. The team has production Redis experience. Adding Streams is an incremental change — new commands, not new infrastructure. This is the only option that meets the 2-week time-to-value constraint.

### Budget

Redis Streams add zero incremental infrastructure cost — we already pay for Redis. Self-hosted Kafka requires additional EC2 instances (minimum 3 brokers), EBS volumes, and monitoring. Managed Confluent Cloud pricing at our throughput would cost thousands per month, exceeding the budget envelope.

## Alternatives Considered

**Apache Kafka** — Kafka is the stronger choice for organizations with dedicated platform engineering teams, massive throughput requirements (millions of messages/sec), long-term event replay needs, or multi-team event-driven architectures where decoupled production and consumption across dozens of services justifies the operational investment. We would choose Kafka if our throughput requirement were 10–100× higher, if we had a dedicated infrastructure engineer, or if we needed to replay days or weeks of events for analytics. At our current and projected scale, with our team size and budget, the operational overhead is unjustified.

**RabbitMQ** — Considered but excluded because it lacks native consumer-group semantics (it requires exchange/queue topology per consumer pattern), its message retention model is delete-on-ack (no built-in replay for debugging), and it introduces a second operational system alongside Redis. It would be preferable if we needed sophisticated routing topologies or priority queues, which we do not.

**PostgreSQL SKIP LOCKED (poll-based)** — Considered as the simplest option: a `notifications` table with `SELECT … FOR UPDATE SKIP LOCKED`. Rejected because polling introduces latency (workers must poll at intervals), provides no push-based consumption, and puts write-heavy notification traffic on our already-burdened primary PostgreSQL instance — the same database that suffered connection-pool exhaustion in both cascading-failure incidents.

## Consequences

### Positive

- **Fast time to value** — notification workers can be operational within days on existing Redis infrastructure; no new services to provision or learn.
- **Lower operational risk** — no new distributed system to run; Redis is already monitored, backed up, and understood by the team.
- **Zero incremental cost** — runs on the existing Redis instance.
- **Sufficient performance headroom** — 10× growth target (~5K msg/s) is well within single-instance Redis Streams capacity.
- **Clear upgrade path** — if we eventually outgrow Redis Streams, the producer/consumer interface is a thin abstraction; swapping the backing store requires changing one module, not the entire notification pipeline.

### Negative

- **Memory-bound retention** — Redis holds data in memory; if consumers fall behind and the stream grows beyond `MAXLEN`, unacknowledged messages are evicted. Mitigation: set `MAXLEN ~100000` as a safety cap and alert on `XPENDING` backlog exceeding 1,000 messages.
- **No built-in replay** — once messages are `XACK`-ed and trimmed, they are gone. Unlike Kafka's disk-backed log, there is no facility to replay the last 24 hours of notifications. Mitigation: log every notification event to PostgreSQL before producing to the stream (this is also the idempotency table for exactly-once billing delivery).
- **Single point of failure** — our current Redis instance is a single node. If it goes down, notification production stalls. Mitigation: configure Redis persistence (AOF), add a replica for high availability, and treat Redis unavailability the same as database unavailability — degraded but not data-loss.
- **Consumer-group maturity** — Redis Streams consumer groups lack automatic rebalancing and session-based claim timeouts that Kafka provides. Mitigation: implement a health-check loop in workers that claims `XPENDING` entries older than a threshold (e.g., 30 seconds); this is straightforward at our scale of 2–4 workers.

### Follow-ups

1. Implement the `NotificationBroker` abstraction (producer interface + consumer interface) so the backing store is swappable without touching business logic.
2. Create a `notifications` table in PostgreSQL with a unique constraint on `(notification_type, entity_id, idempotency_key)` for exactly-once delivery of billing events.
3. Set `MAXLEN ~100000` on all notification streams and wire `XPENDING` depth into our alerting.
4. Add a Redis replica for HA before promoting the notification subsystem to production.
5. Revisit this decision if sustained notification throughput exceeds 10,000 msg/s or if the team grows to include a dedicated infrastructure engineer.

## Backlinks

- _(None yet — this is the first ADR.)_