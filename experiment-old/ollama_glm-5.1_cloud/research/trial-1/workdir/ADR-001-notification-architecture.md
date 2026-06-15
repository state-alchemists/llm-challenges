# ADR 001 — Notification Subsystem Message Broker

- **Status**: Proposed
- **Date**: 2026-05-30
- **Deciders**: Engineering team (3 senior, 3 mid-level)
- **Context tags**: notifications, messaging, performance, reliability

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, ~500 req/s peak) handles all notifications — emails, webhooks, and soon WebSocket pushes — synchronously inside the HTTP request cycle. This has caused request timeouts (800 ms average, 8 s spikes), silent delivery failures with no retry, cascading connection-pool exhaustion from slow webhook endpoints (two production incidents this year), and no delivery guarantees for billing-critical notifications ("trial expired", "payment failed") that require exactly-once semantics.

We need to decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery for all notifications and exactly-once where feasible, support WebSocket push notifications within two quarters, and absorb 10x traffic growth without re-architecting.

Constraints that shape this decision:

- **6-person team, no dedicated infrastructure engineer.** Operational burden must be minimal.
- **Redis already in production** for sessions and rate limiting. The team has operational familiarity.
- **No Kafka experience** on the team today.
- **2-week ceiling** on setup before delivering value. This is non-negotiable.
- **Modest budget.** Managed Confluent Cloud at our projected scale is not affordable; self-hosted Kafka requires dedicated resources we do not have.
- **Exactly-once semantics required for billing notifications.** This applies to end-to-end delivery (email/webhook arrives once), not just broker-level deduplication.

## Decision

> We will use Redis Streams as the message broker for the notification subsystem.

Redis Streams already runs on infrastructure we operate, with a team that understands it. The notification workload (even at 10x growth — ~5K req/s peak) is two orders of magnitude below Redis Streams' practical ceiling. Adding a Kafka dependency that nobody on the team has run in production, under a 2-week deadline, with no dedicated infrastructure engineer, is an unjustified risk — especially since Kafka's exactly-once semantics do not eliminate the need for application-level idempotency at the consumer (email provider, webhook endpoint), which we must build regardless.

## Rationale

### Throughput and scale

Redis Streams handles tens of thousands of messages per second on a single instance. Our current peak is ~500 req/s; even projecting 10x growth to ~5K req/s, we use a fraction of that capacity. Kafka's design point — millions of messages per second across distributed partitions — solves a problem we do not have and will not have within the foreseeable scaling horizon.

### Exactly-once semantics

This is the most misunderstood factor. Kafka provides exactly-once processing *within Kafka itself* (idempotent producers, transactional reads across partitions). But our consumers are external systems — email providers (SendGrid, SES) and customer webhook endpoints — that are inherently at-least-once. No broker choice eliminates the need for application-level deduplication (e.g., a PostgreSQL table tracking `(notification_id, target, status)` with a unique constraint) to guarantee that a billing email is sent exactly once.

Therefore, the choice between Kafka and Redis Streams does not change our exactly-once implementation path. We must build an idempotent consumer layer regardless. Redis Streams' at-least-once delivery, combined with a dedup table in our existing PostgreSQL, satisfies the requirement.

### Operational complexity

Kafka requires broker processes, partition management, replica coordination, and monitoring — a non-trivial operational surface. Self-hosted Kafka with KRaft (or ZooKeeper) is a new distributed system our team has never operated. Managed Confluent Cloud solves the ops problem but is expensive at scale and still requires learning Kafka's programming model (consumer groups, partition assignment, offset management, rebalancing).

Redis Streams runs on the Redis instance we already operate. Adding a stream is an `XADD`; consuming is an `XREADGROUP`. Operational complexity is additive, not multiplicative.

### Time-to-value

Under a 2-week constraint, Redis Streams integration means writing producer/consumer code against an existing infrastructure dependency. Kafka means: provisioning a cluster (or signing up for managed service), learning Kafka's programming model, tuning producer/consumer configs, building the consumer framework, and handling rebalancing and partition logic — all before any notification logic ships. The 2-week ceiling makes Kafka impractical.

### Future WebSocket push

Redis Pub/Sub complements Streams for real-time fan-out to WebSocket servers. A Kafka-based approach requires an additional bridge or a different topology entirely. The combination of Streams (durable, ordered processing) and Pub/Sub (ephemeral, real-time push) under a single Redis dependency is architecturally coherent.

## Alternatives Considered

### Apache Kafka

Kafka's strengths are real — strict per-partition ordering, durable log with configurable retention (hours to weeks), mature consumer group protocol, and exactly-once semantics within Kafka. These properties matter for event-sourced domains with high-volume, multi-consumer downstream fan-out (analytics pipelines, event replay, audit logs).

We rejected Kafka because: (1) no team experience and no dedicated infra engineer makes self-hosted operation a reliability risk; (2) the 2-week delivery constraint leaves no room to learn and harden a new distributed system; (3) managed Confluent Cloud exceeds our budget at projected scale; (4) our workload does not require Kafka's primary advantage — high-throughput, multi-consumer log replay — since we have one consumer group (notification dispatch) and short retention needs; (5) exactly-once for external consumers requires application-level idempotency regardless of broker choice, eliminating Kafka's strongest theoretical advantage.

We would revisit Kafka if: our notification volume exceeds 50K msgs/s, we need multi-team event streaming with replay, or we hire dedicated infrastructure engineers and budget for managed Kafka.

### PostgreSQL LISTEN/NOTIFY

Considered briefly as the "simplest possible" option. NOTIFY delivers messages to connected clients in real-time but provides no persistence — if no consumer is connected, the message is lost. This fails the at-least-once delivery requirement for billing notifications. Not viable.

### RabbitMQ

A middle ground: richer routing than Redis Streams, simpler operation than Kafka. Rejected because it introduces a new infrastructure dependency (we run neither RabbitMQ nor Erlang today) with marginal benefit over Redis Streams for a single-consumer-group notification workload. Would reconsider only if we needed complex routing topologies (topic exchanges, fan-out to distinct consumer groups with different routing rules) that Redis Streams does not model well.

## Consequences

### Positive

- **Faster delivery.** Producer and consumer code against an existing Redis instance; no new infrastructure to provision, monitor, or learn. We can ship the first async notification within the 2-week window.
- **Lower operational surface.** One fewer distributed system to operate. Redis is already paged on; Kafka would add a second.
- **Coherent WebSocket path.** Redis Pub/Sub + Streams under the same dependency covers both durable processing and real-time push — no additional broker needed for WebSocket notifications.
- **Sufficient headroom.** Even at 10x current load (~5K req/s), Redis Streams operates comfortably. No re-architecture required within the scaling horizon.
- **Budget-neutral.** No new managed-service costs.

### Negative

- **Memory-bound retention.** Redis Streams hold data in memory. We must set `MAXLEN` and archive processed notifications to PostgreSQL promptly. At projected volumes this is manageable, but it requires discipline — unmonitored streams can grow until Redis evicts keys or OOMs. We mitigate this with `XTRIM` policies and alerting on stream length.
- **No native log replay.** Unlike Kafka's durable log, Redis Streams are consumed and trimmed. If we need to replay notifications from 30 days ago, we read from PostgreSQL, not the stream. This is acceptable — our retention need is processing-time, not audit-time — but it closes off event-sourcing patterns without additional infrastructure.
- **Application-level idempotency required.** At-least-once delivery means consumers may see duplicates on retry. We must implement deduplication (PostgreSQL unique constraint on `notification_id + target`) for billing notifications. This is true regardless of broker, but it adds implementation work we must not defer.
- **Single Redis instance is a SPOD.** If Redis is down, notification production halts. We currently run a single Redis instance. For the notification subsystem, we should plan Redis Sentinel or a replica within one quarter, before the WebSocket launch.
- **Limited consumer group maturity.** Redis Streams consumer groups (XREADGROUP, XPENDING, XCLAIM) are functional but less battle-tested than Kafka's. Edge cases around stuck messages after consumer crashes require active monitoring (periodic XCLAIM of pending entries past the visibility timeout).

### Follow-ups

- **Week 1–2:** Implement `XADD` producer in Flask, `XREADGROUP` consumer worker, PostgreSQL dedup table for billing notifications, retry with exponential backoff, dead-letter stream for permanently failed notifications.
- **Week 3–4:** Add monitoring (stream length, consumer lag via `XPENDING`, dead-letter count), alerting, and a periodic `XCLAIM` sweeper for stuck messages.
- **Before WebSocket launch (Q+2):** Deploy Redis Sentinel or replica for HA; implement Pub/Sub fan-out alongside the existing Streams consumer.
- **Re-evaluate Kafka** if notification volume exceeds 50K msgs/s or the team needs multi-consumer-group event streaming with long retention.