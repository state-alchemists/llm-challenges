# ADR 001 — Notification Subsystem Message Broker

- **Status**: Proposed
- **Date**: 2026-07-30
- **Deciders**: Engineering team (3 senior, 3 mid-level)
- **Context tags**: notifications, messaging, scaling, redis, kafka

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, ~500 req/s peak) handles all notifications — emails, webhooks, and in-app alerts — synchronously inside the HTTP request cycle. This has caused three production incidents:

1. **Request timeouts**: Notifications block responses. Average latency 800 ms, spikes to 8 s during peak hours.
2. **Silent failures**: Downstream provider outages drop notifications with no retry or dead-letter queue.
3. **Cascading failures**: Slow webhook endpoints exhausted the connection pool twice this year, taking down unrelated features.

Additionally, billing-critical notifications ("trial expired", "payment failed") have no delivery guarantee — they are silently dropped on failure.

We need to decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (with exactly-once *effect* for billing events), add real-time WebSocket push within 2 quarters, and handle 10× traffic growth without re-architecting.

**Constraints**:

- 6-person engineering team, no dedicated infrastructure engineer.
- Redis is already in production (session storage, rate limiting).
- No Kafka operational experience on the team.
- Setup and migration must deliver value within 2 weeks.
- Budget does not support managed Confluent Cloud at scale.
- Billing notifications require exactly-once delivery effect.

## Decision

> We will use Redis Streams as the message broker for the notification subsystem.

Redis Streams satisfies the throughput and ordering requirements, aligns with the team's existing operational expertise, and can be production-ready within the 2-week constraint. Exactly-once *effect* for billing notifications is achieved through application-level idempotency keys stored in PostgreSQL — a pattern that works identically regardless of broker, which neutralizes Kafka's in-system exactly-once advantage for our use case (external delivery to email providers and webhook endpoints is inherently at-least-once; true exactly-once requires consumer-side deduplication either way).

## Rationale

### Throughput and scaling

Current peak is ~500 notification events per second. The 10× growth target is ~5,000 msg/s. Redis Streams handles 10,000–100,000 operations per second per node on commodity hardware. Our workload, even at 10×, is well within that range. Kafka's design point of millions of messages per second is unnecessary here — we pay operational complexity for throughput headroom we will not use.

### Exactly-once for billing

This is the constraint most likely to favor Kafka, so it deserves precision. Kafka's exactly-once semantics (idempotent producer, transactional consume-process-produce) guarantee exactly-once *within the Kafka cluster*. Our delivery targets are external — SMTP providers, HTTP webhook endpoints — where no broker can guarantee exactly-once delivery. The correct pattern for billing notifications is:

1. Producer writes the notification event to the stream with a unique `idempotency_key`.
2. Consumer reads the event, checks PostgreSQL for the idempotency key before processing.
3. On duplicate delivery, the consumer finds the key and skips processing.

This deduplication layer is required with either Kafka or Redis Streams. Kafka's intra-cluster exactly-once does not eliminate it. Therefore, this constraint does not differentiate the two options.

### Operational fit

Redis is already operated by this team. Adding Streams uses the same deployment, monitoring, and on-call knowledge. Kafka would introduce: broker cluster provisioning, partition strategy decisions, ZooKeeper or KRaft quorum management, topic lifecycle governance, and a separate monitoring and alerting stack. For a team of 6 with no dedicated infrastructure engineer and no prior Kafka experience, this operational surface area is a significant and unnecessary risk within the 2-week delivery window.

### Time to value

Redis Streams requires: a dedicated Redis instance for notification data (isolated from the session cache), consumer group creation (`XREADGROUP`), and a worker process that reads from the stream and dispatches to email/webhook providers. This can be operational in days. Kafka requires: cluster provisioning, broker configuration, topic design, partition assignment, consumer group configuration, and team ramp-up — realistically weeks before the first notification flows through.

### Real-time WebSocket path

Redis Pub/Sub is the standard complement to Streams for real-time fan-out to WebSocket connections. The architecture is: write event to Stream (durable, for retry), publish a lightweight pointer to Pub/Sub (ephemeral, for instant push). Both primitives are available in the same Redis instance. Kafka has no equivalent low-latency fan-out mechanism; WebSocket push over Kafka requires an additional system (e.g., Socket.io adapter backed by a Redis instance anyway).

## Alternatives Considered

### Apache Kafka

Kafka is the stronger choice on paper for: strict per-partition ordering, long-term message retention with replay from arbitrary offsets, massive horizontal scalability, and mature consumer group coordination.

**Why rejected**: Kafka's advantages are misaligned with our actual constraints. Our message volume is low enough that Redis Streams' ordering guarantees (per-stream, strictly sequential) are sufficient. Our source of truth for notification state is PostgreSQL, not the message log — we do not need multi-day retention and replay. Our team has no Kafka operational experience, and the 2-week delivery window rules out the ramp-up time. Managed Confluent Cloud is explicitly unaffordable at our budget. Self-hosted Kafka would consume a disproportionate share of a 6-person team's capacity for infrastructure that vastly exceeds our throughput needs.

We would choose Kafka if: our throughput requirement exceeded ~50,000 msg/s, we needed multi-service event streaming (not just notifications), we had a dedicated platform engineering team, or our budget supported managed Confluent.

### PostgreSQL LISTEN/NOTIFY + queue tables

Lightest-weight option: write notification rows to a table, use `LISTEN/NOTIFY` to wake workers. Simple to implement, but `LISTEN/NOTIFY` has no delivery guarantee (messages are lost if no listener is connected), no consumer group coordination, and no built-in retry. We would end up rebuilding stream semantics in application code. Rejected because it does not meet the at-least-once delivery requirement without significant custom logic.

### RabbitMQ

Mature message broker with dead-letter exchanges, TTL, and routing. More operationally complex than Redis Streams (separate cluster, separate monitoring, separate expertise) without the throughput justification of Kafka. Rejected because it introduces a new infrastructure dependency with no team experience, similar to Kafka's operational cost but without Kafka's scaling ceiling.

## Consequences

### Positive

- **Fast time to value**: Redis Streams can be production-ready in days, not weeks. The team can ship the async decoupling, retry, and dead-letter handling within the 2-week window.
- **Low operational overhead**: Same technology the team already operates. No new deployment topology, monitoring stack, or on-call runbooks to create from scratch.
- **Budget-neutral**: No additional managed-service costs. A dedicated Redis instance for notifications (isolated from the session cache) runs on a single EC2 instance or ElastiCache node.
- **Adequate throughput**: Handles current peak (~500 msg/s) and 10× growth (~5,000 msg/s) with comfortable headroom.
- **WebSocket-ready**: Redis Pub/Sub + Streams provide a natural architecture for real-time push, which is on the 2-quarter roadmap.

### Negative

- **Retention ceiling**: Redis Streams persistence depends on RDB snapshots or AOF — not the append-only commit log durability of Kafka. If the Redis node loses both memory and disk before a snapshot, in-flight messages are lost. Mitigation: AOF with `fsync everysec` and notification events also recorded in PostgreSQL before stream write (dual-write pattern for billing-critical events).
- **No native replay from offset**: Redis Streams supports `XREAD` from a given ID, but does not have Kafka's compacted topics or long-term retention with arbitrary offset replay. For our use case this is acceptable — PostgreSQL is the source of truth, not the stream. If replay is needed, events are reconstructable from the database.
- **Single-node bottleneck**: Redis Streams on a single instance limits horizontal scaling to the throughput of one node. At our projected volumes this is not a concern, but beyond ~50,000 msg/s or multi-TB stream depths, Redis would need to be re-evaluated. This decision should be revisited if notification volume grows by another order of magnitude.
- **Consumer group immaturity**: Redis Streams consumer groups (`XREADGROUP`, `XPENDING`, `XCLAIM`) are functional but less battle-tested than Kafka's. Edge cases around consumer rebalancing and partition assignment are simpler (single stream, no partitions) but also less flexible.
- **Monitoring gap**: Redis does not expose the same depth of consumer-lag metrics as Kafka's ecosystem (Burrow, Confluent Control Center). We will need to build or adopt lightweight monitoring (e.g., tracking `XPENDING` counts) as part of the implementation.

### Follow-ups

1. Provision a dedicated Redis instance for notifications (isolated from the session/rate-limiting instance) with AOF persistence enabled.
2. Implement the notification worker: `XREADGROUP`-based consumer with exponential backoff retry, dead-letter stream for permanently failed messages, and PostgreSQL idempotency-key deduplication for billing events.
3. Add `XPENDING`-based monitoring and alerting for consumer lag and dead-letter depth.
4. Migrate billing-critical notifications first (highest risk, highest value from exactly-once guarantees).
5. Design the WebSocket push architecture (Stream for durability, Pub/Sub for fan-out) as a follow-up in quarter 2.
6. Re-evaluate this decision if sustained notification throughput exceeds 10,000 msg/s or if multi-service event streaming becomes a requirement.

## Backlinks

- *(No prior ADRs — this is the first.)*