# ADR 001 — Notification Subsystem Message Broker

- **Status**: Proposed
- **Date**: 2026-06-19
- **Deciders**: Engineering team (3 senior, 3 mid-level)
- **Context tags**: notifications, async-processing, infrastructure, scaling

## Context

The notifications module currently sends emails and webhooks synchronously inside the HTTP request cycle on our Python/Flask monolith. This causes request timeouts (800 ms average, 8 s spikes at peak), silent failures with no retry or dead-letter queue, and two cascading outages this year where slow webhook endpoints exhausted the database connection pool. Billing-critical notifications ("trial expired", "payment failed") have no delivery guarantees.

The platform serves 85,000 monthly active users with ~500 req/s at peak and ~2 M tasks created per month. We need to:

1. Decouple notification delivery from the HTTP request cycle.
2. Support retry with exponential backoff and a dead-letter queue.
3. Guarantee at-least-once delivery for billing events, with exactly-once semantics where feasible.
4. Add real-time WebSocket push notifications within two quarters.
5. Handle 10× traffic growth (~5,000 req/s peak) without re-architecting.

Hard constraints:

- **Team**: 6 engineers, no dedicated infrastructure engineer.
- **Experience**: Redis is already in production for sessions and rate limiting; no one on the team has operated Kafka.
- **Timeline**: The solution must deliver value within 2 weeks of starting.
- **Budget**: Modest — managed Confluent Cloud at full scale is not affordable today.

We evaluated two stream-oriented message brokers: Apache Kafka and Redis Streams.

## Decision

> We will use Redis Streams as the message broker for the notification subsystem.

Redis Streams runs on our existing Redis instance, requires no new infrastructure, and the team already has operational experience with Redis. Its throughput (single-digit millions of messages per second on modern hardware) exceeds our 10× growth target by two orders of magnitude. Exactly-once semantics for billing notifications are achieved through idempotent consumers backed by a PostgreSQL idempotency table — the same pattern used in Kafka deployments that need application-level deduplication anyway.

## Rationale

### Throughput and scale

Our current peak is ~500 req/s; the 10× target is ~5,000 req/s. Redis Streams on a single node handles millions of messages per second. Even with overhead from consumer-group coordination and pending-entry-list (PEL) tracking, our projected load is well within a single Redis instance. Kafka's throughput advantage (10 M+ msg/s in a cluster) is real but irrelevant — we are orders of magnitude below the ceiling where that advantage matters.

### Operational complexity

Kafka requires either ZooKeeper or KRaft for metadata, plus broker nodes, topic configuration, partition planning, and monitoring of consumer lag across a new control plane. For a 6-person team without a dedicated infrastructure engineer, operating Kafka is a significant ongoing burden. Redis Streams adds one data structure to an already-running Redis instance. Setup time for Redis Streams is measured in hours; Kafka's is measured in weeks.

### Exactly-once semantics

Kafka provides exactly-once semantics (EOS) through idempotent producers and transactional consumers — but this requires the `transactional.id` protocol, careful consumer configuration, and a transaction coordinator. In practice, many teams disable Kafka transactions for latency reasons and implement idempotent consumers instead. Our billing-notification exactly-once requirement is satisfied by:

1. **At-least-once delivery** from Redis Streams (messages remain in the stream until explicitly acknowledged via `XACK`).
2. **Idempotent consumers** that check a PostgreSQL idempotency table (dedup key = `notification_type + entity_id + event_id`) before processing any billing event.

This is the same pattern recommended for Kafka deployments where the consumer writes to an external database — which is exactly our case.

### Team and timeline fit

The team has operational Redis experience (monitoring, persistence, failover on our existing instance). No one has run Kafka in production. Two weeks does not allow time to learn Kafka operations, set up a cluster, harden it for production, and migrate the notification pipeline. Redis Streams lets us ship a working async notification system within the deadline by reusing existing infrastructure and skills.

### Budget

Self-managed Kafka on AWS requires 3+ broker nodes (minimum for fault tolerance), plus monitoring infrastructure. Managed Confluent Cloud at our projected throughput would cost significantly more than our current Redis setup. Redis Streams adds zero marginal infrastructure cost — it runs on the instance we already pay for.

### Consumer groups and ordering

Redis Streams supports consumer groups natively (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`). Within a single stream, messages are strictly ordered by insertion time. Kafka guarantees ordering within a partition, not across partitions — our notification streams are naturally single-partition workloads (all notifications of a type in one stream), so Redis Streams' per-stream ordering is equivalent to Kafka's per-partition ordering for our use case.

### Message retention

Redis Streams uses `MAXLEN` trimming (approximate or exact) to bound stream length. For our notification workload, messages are consumed and acknowledged within seconds; we configure `MAXLEN ~100,000` as a safety cap and rely on `XACK` + `XDEL` for normal lifecycle. Kafka's configurable log retention (time-based or size-based) is more flexible for long-term event replay, but we do not have a replay requirement today — notifications are fire-and-forget with retry.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for event streaming at scale. It offers durable log retention, partition-level ordering, strong consumer-group coordination, and true exactly-once semantics via transactions. It would be the right choice if our throughput requirements were 100× higher (hundreds of thousands of messages per second), if we needed long-term event replay, or if we were building a company-wide event backbone serving multiple independent consumer teams.

We rejected Kafka because: (1) the team has no operational experience and no dedicated infra engineer, making the operational burden unacceptable; (2) the 2-week timeline cannot accommodate Kafka cluster setup, configuration, and production hardening; (3) managed Kafka exceeds our budget; (4) Kafka's throughput and retention advantages are overkill for our current and projected scale. We would revisit Kafka if throughput requirements exceed what a single Redis node can handle, or if we need durable multi-day event replay across multiple independent consumer teams.

### PostgreSQL LISTEN/NOTIFY with a queue table

Considered briefly as the simplest option — a `notification_queue` table with `SELECT ... FOR UPDATE SKIP LOCKED` and PostgreSQL's `LISTEN/NOTIFY` for wake-up. This avoids introducing any new technology but does not provide consumer groups, complicates horizontal scaling (all workers hit the same table), and pollutes the OLTP database with queue workload. We rejected this because the notification pipeline should not share write capacity with the application's primary database, and the 10× growth target makes single-table contention a real risk.

## Consequences

### Positive

- **Fast time to value**: Async notification processing ships within the 2-week deadline by reusing our existing Redis instance.
- **Zero marginal infrastructure cost**: No new servers, no new managed service, no new vendor contract.
- **Team leverage**: Engineers operate what they already know — Redis persistence, replication, and monitoring are solved problems for this team.
- **Sufficient headroom**: A single Redis node handles ~5,000 req/s with comfortable margin; horizontal scaling via Redis Cluster is available if needed later.
- **Consumer groups**: Built-in `XGROUP`/`XACK` provides the coordination primitives needed for parallel workers, retry, and dead-letter handling.
- **At-least-once delivery**: Messages persist until acknowledged; no silent drops.

### Negative

- **No true exactly-once at the broker level**: Exactly-once for billing notifications depends on application-level idempotency (PostgreSQL dedup table). This works but requires discipline — every billing consumer must implement the idempotency check. A missed check results in a duplicate notification.
- **Message retention is bounded**: Redis Streams trim to a maximum length; unconsumed messages beyond `MAXLEN` are lost. If a consumer falls behind by more than 100,000 messages, notifications are dropped. This is unlikely at our scale but possible during a prolonged outage.
- **Single-node availability**: Our current Redis setup is a single instance (not a cluster). A Redis outage takes down the notification pipeline. This is mitigated by Redis persistence (AOF/RDB) and our existing Redis restart playbook, but it is a single point of failure.
- **Re-evaluation needed at higher scale**: If traffic grows beyond ~50,000 req/s, or if we need multi-day event replay, or if multiple independent teams need their own consumer topologies, Redis Streams becomes a limiting factor and Kafka (or a similar distributed log) becomes the better choice.
- **Operational coupling**: Notification throughput competes with session and rate-limiting traffic on the same Redis instance. Under extreme load, a notification spike could evict session keys. We mitigate this by using separate logical databases (`SELECT 0` for sessions, `SELECT 1` for streams) and monitoring memory pressure.

### Follow-ups

- Implement the idempotency table in PostgreSQL for billing-notification deduplication.
- Configure a separate Redis logical database (`SELECT 1`) for notification streams to isolate memory pressure from session storage.
- Set `MAXLEN ~100,000` on notification streams and monitor `XPENDING` lag as a key operational metric.
- Add a dead-letter consumer that reads the PEL for messages that exceed the max retry count and writes them to a `notification_dead_letters` PostgreSQL table for manual inspection.
- Document the Redis Streams operational runbook (consumer-group recovery, PEL inspection, `XCLAIM` for stalled messages).
- Re-evaluate Kafka if sustained throughput exceeds 50,000 msg/s or if a company-wide event backbone is needed.

## Backlinks

- *(None yet — this is the first ADR.)*