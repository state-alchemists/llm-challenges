# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our Python/Flask monolith currently sends email and webhook notifications synchronously inside the HTTP request cycle. At 85,000 monthly active users and peak loads of ~500 req/s, this has produced:

- **Request timeouts**: average notification latency 800ms, spiking to 8s during peak hours
- **Silent failures**: no retry or dead-letter queue when providers or webhook endpoints are down
- **Cascading failures**: slow webhook endpoints have caused connection pool exhaustion, taking down unrelated features (two incidents this year)
- **No delivery guarantees**: billing-critical notifications (trial expiry, payment failure) are not guaranteed to be delivered exactly once

We must decouple notification dispatch from the HTTP request cycle, add retry with exponential backoff, guarantee at-least-once delivery for all notifications and exactly-once semantics for billing events, and lay groundwork for real-time WebSocket push within two quarters. The solution must also accommodate 10x traffic growth without a fundamental re-architecture.

**Team and infrastructure constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis is already deployed in production (session storage, rate limiting)
- No Kafka operational experience on the team
- Maximum two weeks of setup and migration work before delivering production value
- Modest budget: managed Confluent Cloud is not affordable at target scale

## Decision

We will adopt **Redis Streams** as the messaging backbone for the notification subsystem.

### Justification

Given our team size, existing infrastructure, hard timeline, and budget, Redis Streams is the only option that lets us ship a resilient, retry-capable, decoupled notification pipeline within two weeks. Kafka is technically superior for massive-scale exactly-once streaming, but the operational burden of self-hosting Kafka—without an infrastructure engineer and without prior team experience—would consume our entire two-week window just standing up brokers, ZooKeeper/KRaft, monitoring, and partition tuning, before a single notification is moved off the critical path.

Redis Streams delivers the properties we need at our current and projected scale:

| Property | Redis Streams Fit |
|---|---|
| **Throughput** | A single Redis instance handles >100k ops/sec. Even at 10× peak (~5,000 req/s, which could generate ~15,000 messages/sec with multi-channel notifications), we remain well within headroom. If we eventually saturate a single node, Redis Cluster shards streams horizontally without changing the programming model. |
| **Ordering guarantees** | Redis Streams preserves total order within a single stream key. For our use case—per-user or per-task notification streams—this gives us the ordering we need. We can partition by user or task ID to maintain relevant sequencing. |
| **Message retention** | Streams support maxlen trimming (count-based) and time-based expiration via TTL on the stream key. We will configure a retention window of 7 days and a maximum length of 1M entries per stream, giving us enough buffer for consumer lag and replay debugging without unbounded memory growth. |
| **Consumer groups** | Native consumer groups (XGROUP, XREADGROUP, XACK) provide automatic message distribution across workers, per-consumer PEL (Pending Entries List) tracking, and claim-on-failure for stalled messages. This gives us the at-least-once foundation we need with minimal custom code. |
| **Exactly-once semantics** | Redis Streams does not natively provide exactly-once semantics (no idempotent producer / transactional writes like Kafka). We will achieve practical exactly-once for billing notifications by combining: (1) idempotent downstream providers (email/SMS APIs that accept idempotency keys), (2) a deduplication log in PostgreSQL keyed by `(notification_type, recipient, idempotency_key)` with a 24-hour uniqueness window, and (3) atomic acknowledgment only after successful provider dispatch. This is sufficient because billing notification volume is low-frequency relative to task updates. |
| **Operational complexity** | We already run Redis for sessions and rate limiting. Adding Streams uses the same deployment, monitoring, backup, and failover procedures the team already understands. No new infrastructure stack, no broker quorum management, no partition rebalancing ceremonies. |

Additionally, Redis Streams integrates cleanly with our planned WebSocket push feature: the same Redis deployment can run Pub/Sub alongside Streams, letting us broadcast real-time events to connected clients without introducing a second message broker.

## Consequences

### Positive
- **Fast time-to-value**: the team can begin migrating notifications off the synchronous path within days, not weeks, because no new infrastructure needs to be provisioned or learned.
- **Low operational risk**: same tooling, metrics, and runbooks we use today for Redis sessions.
- **Cost efficiency**: zero new infrastructure spend; we scale vertically or add Redis Cluster shards only when metrics prove it necessary.
- **Unified real-time path**: Pub/Sub co-existence makes the WebSocket push roadmap simpler.
- **Sufficient headroom**: 10× growth still fits comfortably inside Redis's performance envelope.

### Negative
- **Exactly-once is application-level, not broker-level**: we must maintain deduplication state in PostgreSQL and rely on idempotent provider APIs. A bug in our consumer logic could theoretically duplicate a billing notification. This risk is mitigated by the low volume of billing events and by comprehensive integration tests around the deduplication path.
- **Retention model is less flexible than a log**: Kafka's immutable partitioned log allows arbitrary replay from any offset. Redis Streams trims entries, so deep historical replay is bounded by maxlen/TTL. For our notification domain, 7 days is ample; if we need longer audit trails, we will archive dispatched events to PostgreSQL or S3.
- **No native partition rebalancing for scale**: while Redis Cluster can shard streams, it does not offer the seamless horizontal partition scaling of Kafka topics. At truly massive scale (well beyond 10×) we would likely need to migrate to Kafka or another log-based broker.
- **Memory-bound storage**: Streams live in RAM (or Redis on-disk configurations, which trade latency). Retention must be actively managed to prevent memory pressure, especially as notification volume grows.

## Alternatives Considered

### Apache Kafka

Kafka was evaluated as the alternative because it offers native exactly-once semantics (idempotent producers + transactions), durable log-based retention, and seamless horizontal scaling via topic partitioning.

**Why it was rejected:**

1. **Operational complexity exceeds team bandwidth**: running a production Kafka cluster (minimum 3 brokers plus ZooKeeper or KRaft controllers, replication tuning, partition rebalancing, and comprehensive monitoring) demands expertise we do not have and cannot acquire safely inside a two-week window.
2. **Timeline risk**: with no dedicated infrastructure engineer, the probability of a misconfigured broker, replication lag, or consumer group rebalance storm during our first week in production is unacceptably high. A single incident would violate our goal of decoupling notifications quickly and safely.
3. **Budget constraint**: managed Kafka (Confluent Cloud, MSK) would solve the operational burden but is explicitly ruled out by our modest budget at target scale. Self-hosting on AWS EC2 introduces new compute costs plus the hidden cost of team time spent on operations.
4. **Exactly-once is not worth the trade-off at this scale**: while Kafka's exactly-once is elegant, the volume of billing-critical notifications is low enough that an application-level deduplication layer on top of Redis Streams is simpler, cheaper, and faster to validate. We can revisit Kafka if our scale or exactly-once requirements outgrow this pragmatic approach.

**Conclusion**: Kafka is the superior platform for massive-scale event streaming, but for a 6-person team without infrastructure specialization, a 2-week value horizon, and a modest budget, Redis Streams delivers the required capabilities with far lower operational risk.
