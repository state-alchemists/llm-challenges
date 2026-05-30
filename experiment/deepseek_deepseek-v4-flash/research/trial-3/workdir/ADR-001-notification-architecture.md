# ADR 001 — Notification Subsystem: Redis Streams over Apache Kafka

- **Status**: Proposed
- **Date**: 2026-05-30
- **Deciders**: Engineering Team
- **Context tags**: messaging, notifications, async-processing, infrastructure

## Context

The notifications module sends emails and webhooks when tasks are updated, assigned, or completed. It currently runs synchronously inside the HTTP request cycle of a Python/Flask monolith. This coupling causes three operational problems:

1. **Request timeouts**: Email and webhook calls block the HTTP response. Average latency is 800 ms, spiking to 8 s at peak.
2. **Silent failures**: Downstream failures (email provider, webhook endpoint) drop notifications silently — no retry, no dead-letter queue.
3. **Cascading failures**: Slow webhook endpoints have twice this year caused PostgreSQL connection pool exhaustion, taking down unrelated features.

Additionally, billing-critical events (trial expiry, payment failure) require at-least-once delivery with exactly-once semantics where feasible — the current architecture guarantees none of this.

We need to decouple notification delivery from HTTP request handling, add retry with exponential backoff, and lay groundwork for real-time WebSocket push within two quarters. The system operates at 500 req/s peak (~2M tasks/month) and must scale to 10× that without a re-architecture.

### Constraints

- Engineering team of 6 (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already runs in production for session storage and rate limiting.
- Zero Kafka experience on the team.
- Setup and initial value delivery must complete within 2 weeks.
- Budget is modest — managed Confluent Cloud is not affordable at full scale.
- Billing notifications demand exactly-once semantics.

## Decision

> We will use **Redis Streams** for the async notification queue.

The HTTP request cycle will publish notification events via `XADD` to a Redis stream. A set of consumer workers (Python processes, scaled behind a supervisor or ECS service) will consume events using `XREADGROUP`, process delivery (email, webhook), acknowledge with `XACK`, and move failed events to a retry stream with exponential backoff via `XCLAIM`/`XPENDING`.

Exactly-once semantics for billing notifications will be achieved at the application layer: each event carries a unique, idempotent ID derived from the domain event, and consumers deduplicate against a PostgreSQL unique constraint before processing.

## Rationale

**Redis Streams wins on every constraint that differentiates the two options at our scale.**

*Operational complexity.* Redis is already deployed, monitored, and backed up. The team knows its failure modes, memory limits, and configuration surface. Adding Streams means learning one new data type and three commands (`XADD`, `XREADGROUP`, `XACK`), not a new JVM cluster with ZooKeeper/KRaft, broker configuration, partition rebalancing, and GC tuning. For a 6-person team with no infrastructure specialist, this is the decisive factor.

*Time to value.* The first notification can flow through Redis Streams in days, not weeks. Kafka would require provisioning a separate cluster, learning the ecosystem, writing a schema registry migration, and debugging the first consumer group rebalance — well beyond the 2-week window.

*Throughput.* Current peak is 500 req/s. At 10× growth, 5,000 notification events per second is well within a single Redis instance's capability (~100,000 ops/s on modest hardware). Kafka's million-msg/s throughput buys nothing at this scale.

*Exactly-once semantics.* Kafka provides EOS natively via transactions and idempotent producers. Redis Streams does not — but the application-layer pattern (idempotent event IDs + PostgreSQL dedup) is straightforward, well-documented, and places the correctness logic where the team already lives: in application code, not infrastructure config. Billing events are <5% of total notification volume, so the per-event dedup overhead is negligible.

*Existing infrastructure.* Redis Streams requires no new servers, no new DNS entries, no new monitoring dashboards, and no new backup strategy. Kafka would add a minimum of 3 broker nodes plus ZooKeeper or KRaft controllers.

*WebSocket roadmap.* Redis Pub/Sub (or a consumer bridge to a WebSocket server) integrates naturally with the same Redis deployment the Streams workers already talk to. Kafka requires a separate bridge service.

## Consequences

### Positive

- **Zero new infrastructure.** Redis is already in production; Streams is just a new data structure on the same instance.
- **Fastest path to value.** The first consumer worker can be written, deployed, and producing value within one sprint.
- **Low learning curve.** Three Redis commands cover the producer and consumer patterns. Any mid-level engineer on the team can be productive with Streams in an afternoon.
- **Good enough throughput.** A single Redis instance handles 100k+ ops/s — 20× headroom above the 10× growth target (5,000 req/s). We do not need horizontal partitioning at this scale.
- **Simple retry model.** `XPENDING` + `XCLAIM` provides the backlog view and consumer failure recovery needed for exponential backoff without a separate dead-letter infrastructure.
- **Natural WebSocket integration.** The same Redis deployment can host a Pub/Sub channel for real-time push, keeping the 2-quarter WebSocket target on the same operational surface.

### Negative

- **No native exactly-once.** Consumers must implement idempotency at the application layer. This adds a small per-event dedup query to PostgreSQL for billing-critical notifications.
- **Memory-bound retention.** Stream entries live in RAM. At 10× scale with high event volume, we must configure `MAXLEN` trimming aggressively and accept a shorter replay window than disk-backed Kafka. For this use case (notification delivery, not audit log), hours-to-days of replay is sufficient.
- **No automatic rebalancing.** If a consumer worker dies, its pending messages remain unacknowledged until another worker explicitly claims them. The team must build a small consumer-heartbeat and claim cycle (standard pattern, but it requires code).
- **No ecosystem.** Kafka Connect, KStreams, and Schema Registry do not exist for Redis Streams. If in the future we need to stream notifications to a data lake or run complex stream joins, we will need to migrate. That migration is not free.
- **Scaling ceiling.** Beyond ~50k sustained msg/s, a single Redis instance becomes the bottleneck and we would need Redis Cluster with key-level sharding, which complicates consumer group semantics. We do not expect to hit this ceiling for 3+ years based on current growth.

### Follow-ups

- Instrument Redis Stream lag (`XLEN` vs consumer group cursor) as a P0 monitoring metric.
- Add a unique `event_id` column to PostgreSQL for billing notification dedup before any Streams code ships.
- Implement exponential backoff via a secondary retry stream with tiered delays (30s, 2m, 10m, 1h, 6h → DLQ).
- Prototype a WebSocket broadcaster that bridges from Redis Streams or Pub/Sub to a WebSocket server within the next quarter.

## Alternatives Considered

**Apache Kafka** — Rejected because the constraints heavily penalize its strengths and its weaknesses hit our team directly. Kafka's exactly-once semantics, disk-backed retention, and automatic consumer rebalancing are genuinely superior to Redis Streams. However, Kafka requires a separate multi-node cluster, JVM tuning, and ongoing broker administration. With zero Kafka experience on a 6-person team and no dedicated infrastructure engineer, the operational risk of self-hosted Kafka is unacceptable. Managed Confluent Cloud is ruled out by budget. Additionally, the 2-week setup window disappears entirely when the team has to learn Kafka fundamentals first. We would have chosen Kafka if: (a) our throughput requirement exceeded 50k msg/s, (b) we needed years-long message retention, (c) we had a dedicated platform/SRE team, or (d) we already ran Kafka in production. None of these hold. Redis Streams covers 100% of the current and near-future requirements at a fraction of the operational cost.

## Backlinks

- [System Context](system_context.md)
