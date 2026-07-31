# ADR-001 — Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-07-31
- **Deciders**: Engineering Team (6 members: 3 senior, 3 mid-level)
- **Context tags**: notifications, messaging, async-processing, reliability

## Context

Our SaaS project management platform (85,000 MAU, ~2M tasks/month, peak ~500 req/s) currently sends emails and webhooks synchronously inside the HTTP request cycle. This has caused:

- **Request timeouts**: Average notification latency 800ms, spikes to 8s during peak hours.
- **Silent failures**: No retry or dead-letter queue when providers are down.
- **Cascading failures**: Slow webhook endpoints have caused connection pool exhaustion, impacting unrelated features.
- **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") must be delivered exactly once, which the current system cannot guarantee.

We must decouple notification delivery from HTTP request processing, introduce retry with exponential backoff, guarantee at-least-once delivery (with exactly-once for billing events), and support a 10× traffic growth target without re-architecting.

### Constraints

- **Team size and expertise**: 6 engineers, no dedicated infrastructure engineer, no prior experience operating Kafka.
- **Existing infrastructure**: Redis is already in production (session storage, rate limiting). We run on AWS with a Python/Flask monolith and PostgreSQL.
- **Timeline**: Must deliver value within 2 weeks; setup and migration cannot exceed this window.
- **Budget**: Modest; managed Kafka (Confluent Cloud) at full scale is not affordable today.
- **Exactly-once requirement**: Billing notifications require exactly-once delivery semantics.

## Decision

We will use **Redis Streams** as the message backbone for the notification subsystem.

Redis Streams provides the persistence, consumer-group semantics, and bounded complexity we need, while leveraging infrastructure the team already operates in production. We will implement exactly-once delivery for billing-critical events at the application layer using PostgreSQL-backed idempotency keys, because Redis Streams natively guarantees at-least-once delivery, not exactly-once.

## Consequences

### Positive

- **Operational familiarity**: The team already runs Redis for sessions and rate limiting. Adding Streams requires no new infrastructure, deployment patterns, or monitoring stack. This minimizes operational risk for a team without a dedicated infrastructure engineer.
- **Speed to value**: We can ship an async notification pipeline with retry logic within the 2-week constraint. Redis Streams consumer groups are simpler to configure and operate than Kafka consumer groups, which involve partition rebalancing protocols and broker coordination.
- **Cost efficiency**: No new AWS infrastructure is required. We avoid the fixed cost of a Kafka cluster (minimum 3 brokers for production HA) or a managed service.
- **Throughput adequacy**: Redis Streams can sustain tens of thousands of messages per second on a single node. Our peak of ~500 req/s and 10× target of ~5,000 req/s are well within this capacity.
- **Ordering guarantees**: Messages within a single Redis Stream are strictly ordered by ID. For our use case (per-user or per-project notification streams), this ordering is sufficient and avoids the cross-partition ordering complexity of Kafka.
- **Consumer group support**: Redis Streams supports consumer groups with automatic claim and pending-entry-list (PEL) tracking, enabling retry and dead-letter semantics without external tooling.
- **Future WebSocket push alignment**: Redis Pub/Sub (already available in our Redis instance) can be layered on top of Streams for real-time WebSocket delivery within the next two quarters, reusing the same infrastructure.

### Negative

- **Native exactly-once gap**: Redis Streams provides at-least-once delivery. Billing notifications require exactly-once semantics, which we must enforce ourselves via PostgreSQL idempotency keys. This adds application complexity and a database dependency for deduplication.
- **Message retention limits**: Redis is memory-optimized. While AOF/RDB persistence is available, long-term message retention and disk-based replay are weaker than Kafka's log-based storage. We must configure `MAXLEN` carefully and accept that deep historical replays are not a first-class feature.
- **Operational scaling ceiling**: If we grow beyond what a single Redis primary (with replicas) can handle, we will need to shard or migrate. Kafka scales horizontally by adding partitions and brokers more naturally. We accept this trade-off because our 10× growth target still fits a single well-provisioned Redis node.
- **Weaker ecosystem**: Kafka has a richer ecosystem (Kafka Connect, schema registry, mature exactly-once stream processing). We will build retry, dead-letter, and monitoring logic ourselves rather than using off-the-shelf components.

### Follow-ups

1. Implement PostgreSQL idempotency table (`notification_idempotency_keys`) with TTL cleanup for billing events.
2. Define Redis Stream `MAXLEN` and consumer-group `BLOCK`/`COUNT` policies per notification type.
3. Build dead-letter stream and alerting for messages that exceed retry thresholds.
4. Document operational runbook for Redis Streams monitoring (PEL growth, memory usage, consumer lag).

## Alternatives Considered

### Apache Kafka

Kafka was rejected because its operational complexity exceeds our team's capacity and timeline.

- **Operational complexity**: Kafka requires a cluster of at least 3 brokers (plus ZooKeeper or KRaft) for production availability. Partitioning strategy, replication factors, consumer rebalancing, and broker maintenance demand expertise we do not have on a 6-person team without an infrastructure specialist.
- **Experience gap**: No team member has operated Kafka in production. The learning curve for tuning, monitoring, and troubleshooting Kafka consumer groups and partition skew would consume the majority of our 2-week window before delivering any value.
- **Cost**: Self-hosting on EC2 introduces new infrastructure costs. Managed Confluent Cloud is explicitly out of budget at full scale.
- **Advantages we cannot leverage**: Kafka's superior throughput (hundreds of thousands of messages per second) and native exactly-once semantics (idempotent producers + transactions) are compelling, but our peak load (~500 req/s) does not justify the infrastructure overhead. We would choose Kafka if our throughput requirement were 100× higher, if we had dedicated infrastructure staff, or if managed Kafka were within budget.
