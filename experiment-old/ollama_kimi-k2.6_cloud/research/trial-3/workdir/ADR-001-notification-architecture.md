# ADR-001: Notification Architecture — Kafka vs Redis Streams

**Status:** Proposed

**Date:** 2026-05-30

---

## Context

Our SaaS project management platform currently processes notifications (emails, webhooks) synchronously inside the Flask HTTP request cycle. At 85,000 MAU and peak loads of ~500 req/s, this produces:

- **Request timeouts**: average latency 800ms, spiking to 8s during business hours
- **Silent failures**: dropped notifications when downstream providers are unreachable, with no retry or dead-letter mechanism
- **Cascading failures**: slow webhook endpoints have caused two connection-pool exhaustion incidents this year, impacting unrelated features
- **No delivery guarantees**: billing-critical notifications (trial expiry, payment failure) lack exactly-once semantics

We must decouple notification delivery from the request cycle, add retry with exponential backoff, and guarantee at-least-once delivery for all events and exactly-once semantics for billing events. Within two quarters we also need to support real-time WebSocket push. The architecture should sustain 10× traffic growth (5,000 req/s peak) without a ground-up rewrite.

**Team & operational constraints:**
- 6 engineers (3 senior, 3 mid-level); **no dedicated infrastructure engineer**
- Redis already runs in production (sessions, rate limiting)
- **Zero Kafka operational experience** on the team
- Migration must deliver value within **2 weeks**
- Modest budget; managed Confluent Cloud is not viable at target scale

---

## Decision

**Adopt Redis Streams as the notification backbone.**

We will extend our existing Redis deployment with a dedicated Streams instance (or logical DB) to act as the asynchronous message bus for email, webhook, and future WebSocket push notifications. Exactly-once semantics for billing-critical events will be enforced at the **application layer** via an idempotency table in PostgreSQL (event UUID + consumer checkpoint), rather than relying on the transport itself.

---

## Justification

### 1. Operational fit for a 6-person team without infrastructure specialists

Self-hosted Apache Kafka requires a minimum of three brokers plus ZooKeeper/KRaft for high availability, partition rebalancing, ISR (In-Sync Replica) management, and careful JVM tuning. Operating this safely demands either a dedicated platform engineer or significant on-call investment. Redis Streams, by contrast, is a single-process extension of the data structure server we already run, monitor, and back up. The operational surface area is orders of magnitude smaller.

### 2. Two-week migration window

With Redis Streams we can:
- Re-use existing Redis client libraries, monitoring (Redis Insight, CloudWatch Redis metrics), and Terraform/CloudFormation definitions.
- Stand up a Streams endpoint in days, not weeks.
- Migrate notification call sites incrementally without a "big-bang" cluster provisioning phase.

A production-grade Kafka deployment—from broker provisioning, security configuration, and consumer-group tuning to operational runbooks—cannot be completed safely by a part-time owner inside two weeks.

### 3. Throughput and scaling headroom

Current peak: ~500 req/s. Target: 5,000 req/s (10× growth).

A single Redis node can sustain **tens of thousands of stream operations per second**. At our 10× target we remain well within single-node headroom, whereas Kafka’s distributed design only begins to show its advantage at hundreds of thousands of events per second. We are not bottlenecked by Redis throughput; we are bottlenecked by team bandwidth.

### 4. Ordering, retention, and consumer-group semantics

Redis Streams provides:
- **Strict FIFO ordering** within a single stream key, sufficient because notifications are naturally partitioned by workspace or user shard.
- **Consumer groups** with auto-claiming of pending messages, giving us built-in retry and dead-letter behaviour via `XPENDING` and `XCLAIM`.
- **Bounded retention** (`MAXLEN` / `MINID`) that prevents unbounded disk growth—a concern for our modest budget.

### 5. Exactly-once for billing events

Kafka offers native exactly-once via idempotent producers and transactions, but **true exactly-once delivery is impossible without idempotency at the consumer side** (email gateways and webhook endpoints can still duplicate). We will therefore:
1. Generate a deterministic UUID per billing event at the producer (Flask app).
2. Write a deduplication record to PostgreSQL (`notification_idempotency` table: `event_uuid`, `processed_at`) inside the consumer’s delivery transaction.
3. ACK the Redis message only after PostgreSQL commit succeeds.

This pattern gives us **end-to-end exactly-once** that is resilient to both Redis redeliveries and downstream provider retries.

### 6. Path to WebSocket push

Redis Streams lives in the same runtime ecosystem as Redis Pub/Sub. Our planned real-time push feature can reuse the same connection pool and infrastructure, avoiding a second distributed system in the stack.

---

## Consequences

### Pros

- **Low operational overhead**: extends existing in-house expertise and monitoring.
- **Rapid time-to-value**: fits inside the mandated 2-week migration window.
- **Adequate throughput**: single-node Redis Streams handles 5,000 req/s with headroom to spare.
- **Built-in retry mechanics**: consumer groups, pending-entry lists, and `XCLAIM` give us at-least-once delivery and dead-letter behaviour out of the box.
- **Unified stack**: future WebSocket push can use Redis Pub/Sub without adding new infrastructure.
- **Cost-effective**: no additional licensing or managed-service fees at our scale.

### Cons

- **Durability weaker than Kafka**: Redis persists via AOF/RDB; a catastrophic node failure between writes and fsync can lose a small window of messages. Mitigation: use AOF `always` for the Streams instance and cross-AZ replication.
- **No native exactly-once transport semantics**: we must build and maintain the PostgreSQL idempotency layer. This adds application complexity and a database write per billing event.
- **Horizontal scaling eventually hits a ceiling**: if we exceed ~50,000 req/s, a single Redis primary becomes a bottleneck and Redis Cluster or a migration to Kafka would be required. This is acceptable because our 10× target is 5,000 req/s, leaving a further 10× buffer before the ceiling.
- **Retention management is manual**: stream trimming (`MAXLEN`) must be tuned per use case, unlike Kafka’s time-based retention policies.

---

## Alternatives Considered

### Apache Kafka — Rejected

Kafka was rejected **primarily on operational grounds**, not on technical capability:

- **Operational complexity**: a minimal HA deployment requires 3+ brokers, KRaft/ZooKeeper ensemble, partition planning, and careful consumer rebalancing tuning. Without a dedicated infrastructure engineer, this creates an unacceptable reliability risk for a six-person team.
- **Learning curve**: no team member has production Kafka experience. The 2-week migration constraint leaves no margin for operational mistakes that could cause message loss or cluster instability.
- **Cost at modest budget**: self-hosted Kafka on EC2 is cheap in raw compute but expensive in engineering time. Managed Kafka (MSK, Confluent) is explicitly ruled out by budget constraints at target scale.
- **Overkill for current throughput**: Kafka’s architectural advantages—massive partition parallelism, tiered storage, and multi-region replication—only become necessary at throughput levels two orders of magnitude above our 10× target.

Kafka remains the correct choice if the team grows to include platform engineering or if throughput crosses ~50,000–100,000 events/sec. At that future point, the idempotency-layer pattern we build today would port cleanly to Kafka consumers.

---

## Action Items

1. Provision a dedicated Redis Streams node (or logical DB) with AOF `appendfsync always`.
2. Implement producer-side UUID generation for all billing events.
3. Create PostgreSQL `notification_idempotency` table and integrate it into the billing-event consumer.
4. Build a generic Streams consumer framework (retry, exponential backoff, dead-letter via `XCLAIM` + separate DLQ stream) for email and webhook workers.
5. Migrate notification call sites incrementally, starting with billing events.
