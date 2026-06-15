# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

---

## Context

The Notifier subsystem sends emails and webhooks when tasks are updated, assigned, or completed. It currently runs synchronously inside the Flask HTTP request cycle. This has caused:

- **Request timeouts**: 800ms average, 8s spikes during peak hours.
- **Silent failures**: Downstream email/webhook outages drop notifications with no retry or dead-letter queue.
- **Cascading failures**: Two incidents this year where a slow webhook drained the connection pool, taking down unrelated features.
- **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") must deliver exactly once; the current system provides no such contract.

### Scaling target (2 quarters)

- Decouple notifications from HTTP request cycle (async processing).
- Retry with exponential backoff.
- At-least-once delivery for billing events; exactly-once where feasible.
- Real-time WebSocket push notifications.
- Handle 10× traffic growth without re-architecting.

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Existing infra**: Redis already in production (session storage, rate limiting). No Kafka running anywhere.
- **Experience**: No team member has operated Kafka in production.
- **Time-to-value**: Must deliver meaningful improvement within 2 weeks of starting.
- **Budget**: Modest. Managed Confluent Cloud is out of scope at full scale.
- **Exactly-once**: Required for billing notifications.

---

## Decision

**Use Redis Streams as the notification message broker.**

The notification pipeline will follow this pattern:

1. Flask handler writes the notification event to a Redis Stream (`notifications:email`, `notifications:webhook`).
2. Background workers (separate Python processes, one per consumer group) consume via `XREADGROUP` with blocking reads.
3. Successful processing is acknowledged with `XACK`, moving the message out of the PEL (Pending Entry List).
4. Failed deliveries are retried via the PEL mechanism: `XAUTOCLAIM` (Redis 7.0+) reclaims stalled messages after the configured idle timeout, with exponential backoff implemented at the consumer.
5. A dead-letter stream (`notifications:dlq`) receives messages that exceed the retry limit.
6. Exactly-once for billing notifications is achieved at the application level: each billing notification carries a unique idempotency key; consumers deduplicate against a PostgreSQL table before executing the side effect.
7. WebSocket push (Q2 target) uses Redis Pub/Sub fed by a consumer that reads from the notification stream, delivering the same architecture without a new broker.

### Why not Kafka

Kafka is the stronger technology on paper: durable log storage, native exactly-once semantics, superior throughput, and a mature consumer-group protocol. However, our constraints make it the wrong choice today. See *Alternatives Considered* for the full comparison.

---

## Consequences

### Pros (Redis Streams)

- **Zero new infrastructure.** Redis is already in production. No new cluster, no new service to monitor, no new port to open in security groups. The same operational knowledge (connection management, memory tuning, failover) applies directly.
- **Fast time-to-value.** A working producer-consumer pipeline can ship in days, not weeks. The team writes `XADD` and `XREADGROUP` calls on familiar ground. No provisioning pipelines, no JVM tuning, no ZooKeeper/KRaft migration to learn.
- **Fits the throughput envelope.** Our peak is ~500 req/s today; at 10× growth it reaches ~5,000 req/s. Redis handles 100,000+ ops/s comfortably on modest hardware. The bottleneck will be email/webhook delivery latency, not the queue.
- **Consumer groups work as needed.** `XREADGROUP` with `>` delivers each message to exactly one consumer in the group. The PEL tracks unacknowledged messages. `XAUTOCLAIM` reassigns messages from failed consumers. This gives us at-least-once delivery and automatic retry with bounded complexity.
- **Natural path to WebSocket push.** Redis Pub/Sub integrates trivially with the stream consumers — the same process that reads the notification stream can publish to a Pub/Sub channel for real-time push. No second broker required.
- **Exactly-once is achievable.** Redis Streams does not provide native exactly-once, but neither does Kafka when the external side effect (email provider API, webhook HTTP call) is outside the transactional boundary. The standard approach — idempotency keys + deduplication table — works identically with either broker. This is a solved problem, not an architecture risk.
- **Lower operational surface.** One fewer distributed system to fail. If Kafka goes down, an entire JVM cluster must be diagnosed; if Redis goes down, we diagnose a single service (and its replica) that the team already understands.

### Cons (Redis Streams)

- **Memory-bound retention.** Redis Streams live in memory, bounded by `MAXLEN`. Long-term message archival requires an external pipeline (dump to S3 or PostgreSQL). For notification events processed in seconds (retries in minutes), this is not a problem, but it rules out using streams as a permanent audit log.
- **No native exactly-once.** The idempotency-key pattern works but adds consumer-side complexity: every billing consumer must check the dedup table before acting, and the dedup check + side effect must be atomic (use the same database transaction when the side effect is PostgreSQL-gated, or a Redis `SET NX` for idempotency key tracking). This is well-understood but must be implemented carefully.
- **Single-stream ordering.** Redis Streams guarantee total ordering only within a single stream. If we shard by notification type (separate streams per channel), cross-stream ordering is lost. For notifications, this is acceptable — email and webhook deliveries are independent concerns.
- **Less ecosystem tooling.** No Kafka Connect, no KSQL, no Confluent Schema Registry. If we later need to pipe notifications into a data lake or run stream joins, Redis Streams requires custom plumbing. At our scale and team size, this is a manageable cost.
- **Single-point-of-failure risk (mitigated).** If the Redis instance goes down, streams are unavailable. Mitigations: Redis Sentinel or ElastiCache with a replica; AOF persistence with fsync every second; a fallback PostgreSQL queue during Redis outages (implemented as a simple `notifications` table with a `status` column, activated via a feature flag).

---

## Alternatives Considered

### Apache Kafka

Kafka is the standard answer for high-throughput, durable event streaming. We rejected it for this use case.

**Where Kafka is stronger:**

- **Native exactly-once semantics.** Idempotent producers + the transactional API guarantee no duplicates between producer and broker. However, this guarantee breaks at the external-side-effect boundary — email and webhook delivery remain at-least-once unless the consumer implements its own idempotency. The advantage over Redis Streams is narrower than it appears.
- **Disk-backed retention.** Kafka retains messages on disk for configurable periods regardless of consumption. This enables replay and serves as a natural audit log. Redis Streams require MAXLEN trimming and external archival for long-term retention.
- **Higher throughput.** Kafka handles millions of messages per second per cluster. Redis Streams on a single instance handle ~100,000 ops/s. At our 10× target of 5,000 req/s, neither is close to its ceiling. Throughput is not a differentiator here.
- **Mature ecosystem.** Kafka Connect, Schema Registry, KSQL Streams, Confluent CLI — rich tooling around the broker. The team doesn't need any of this today, but it's available tomorrow.

**Where Kafka is the wrong choice for us:**

- **Operational cost is too high for a team of 6.** A production Kafka deployment requires: 3+ broker nodes (for replication), ZooKeeper or KRaft quorum, disk provisioning (Kafka is I/O-bound — needs fast, dedicated EBS volumes), monitoring (JMX, Burrow for consumer lag, Cruise Control for partition rebalancing), careful tuning of `acks`, `min.insync.replicas`, `log.retention.ms`, and thread pool sizing. Every incident requires JVM diagnostics, heap dumps, and broker log spelunking. No team member has this muscle memory today.
- **Two-week delivery is unrealistic.** Provisioning and hardening a Kafka cluster for production (networking, IAM, monitoring, backup, DR) takes 2–4 weeks for an experienced team; our team would take longer. Learning the Kafka client model, producer/consumer configuration nuances, consumer-group rebalancing behavior, and exactly-once semantics adds another week. This violates the 2-week constraint.
- **Managed Kafka is out of budget.** Confluent Cloud pricing at our projected 5000 msg/s × ~2 KB/notification = ~10 MB/s throughput would cost approximately $1,500–$3,000/month at minimum. MSK (AWS) is cheaper but still adds ~$500–1,000/month + per-broker overhead. Both exceed a "modest budget" for what Redis Streams delivers at zero added infrastructure cost.
- **It adds complexity we don't need.** Kafka's advantage is scale. At 500–5,000 notifications per second, we are operating far below Kafka's design point. We would absorb Kafka's operational complexity without exercising its performance envelope. This is the wrong trade.

### Apache Pulsar / RabbitMQ

Briefly considered but not evaluated at depth:

- **Pulsar**: Combines a segment-oriented log (like Kafka) with a shared-nothing architecture. Even more moving parts than Kafka (BookKeeper cluster, broker cluster, ZooKeeper). Operational complexity is higher, not lower.
- **RabbitMQ**: Excellent message broker. Lacks the consumer-group semantics needed for our WebSocket push roadmap and the ordered replay capability that Redis Streams provides natively. Would require an additional datastore to complement it.

Both add *new* infrastructure — unlike Redis, which we already run.

---

## Implementation Outline

Not part of this ADR, but included to confirm feasibility:

1. **Week 1**: Add a `redis_streams` producer module to the Flask app. Create a background worker process that reads from `notifications:email` and `notifications:webhook` streams. Ship with at-least-once delivery and exponential-backoff retry. Remove the synchronous notification code path (feature-flagged for rollback).
2. **Week 2**: Add PostgreSQL-backed idempotency table for billing notifications. Wire up dead-letter stream. Set up monitoring: stream lag (`XLEN`), PEL size, DLQ count.
3. **Q2 (WebSocket push)**: Deploy a WebSocket server that subscribes to a Redis Pub/Sub channel. Write a stream consumer that publishes notification events to Pub/Sub. Real-time push without adding a new broker.

**Total new infrastructure**: Zero. Redis Sentinel or ElastiCache for HA was already on the roadmap for sessions.

---

*Authored: 2026-06-15*
