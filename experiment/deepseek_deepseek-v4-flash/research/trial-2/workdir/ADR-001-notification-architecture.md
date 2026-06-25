# ADR-001: Notification Subsystem — Async Decoupling Architecture

**Status:** Proposed

---

## Context

The Notifier subsystem runs synchronously inside the Flask HTTP request cycle. Every task update, assignment, or completion triggers email and webhook dispatch before the response is returned. This design has produced four escalating problems:

1. **Request timeouts** — Average notification latency is 800ms; spikes reach 8s during peak hours, directly inflating P95/P99 response times for core task-management endpoints.
2. **Silent failures** — Email provider or webhook endpoint failures are caught but swallowed. No retry mechanism, no dead-letter queue, no observability.
3. **Cascading failures** — Two incidents in the past year where a single slow webhook exhausted the HTTP connection pool, causing timeouts on unrelated features (authentication, task listing).
4. **No delivery guarantees** — Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once but have no durability or deduplication.

We need to decouple notification dispatch from the request-response cycle and introduce asynchronous processing with retry, backoff, and delivery guarantees.

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infra engineer.
- **Existing infrastructure**: Redis already running in production for session storage and rate limiting.
- **Team experience**: Zero Kafka experience today; already proficient with Redis.
- **Timeline**: Must deliver value in ≤2 weeks of setup and migration work.
- **Budget**: Modest — managed Kafka (Confluent Cloud) at scale is not affordable. Self-hosting must justify its operational cost.
- **Growth target**: Must handle 10× current traffic (~5,000 req/s peak, ~20M tasks/month) without a re-architecture.

---

## Decision

**We will adopt Redis Streams** as the notification queue substrate.

Redis Streams (introduced in Redis 5.0) provide a persistent, append-only log data structure with consumer-group semantics. Every notification event will be written to a stream via `XADD`, processed by consumer workers via `XREADGROUP`, and acknowledged via `XACK`. Failed deliveries are tracked in the Pending Entry List (PEL) and re-dispatched by a consumer claiming mechanism (`XCLAIM`).

This is not a default "use what you know" choice. The technical properties align with our traffic profile, and the operational risk of introducing Kafka at our team size and timeline is the deciding factor.

### Why not Kafka

Kafka offers stronger partitioning semantics, disk-based retention, and a richer ecosystem. It is the correct choice for many systems — just not this one, at this stage. See **Alternatives Considered** below for the full analysis.

---

## Consequences

### Positive

1. **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. Adding streams requires no new VMs, security groups, IAM roles, or DNS records. The operational delta is zero — a weekend change, not a quarter-long project.

2. **Fast time-to-value.** A team that already understands `HSET`, `EXPIRE`, and Pub/Sub can learn `XADD` and `XREADGROUP` in hours. The async dispatch pipeline can be written, tested, and in production within 1 week, well inside the 2-week constraint.

3. **Adequate throughput at our scale.** Current peak is ~500 req/s. At 10× growth the figure reaches ~5,000 req/s, or roughly 12,000–20,000 notification events/s (accounting for per-task fan-out). A single Redis 7 instance handles 100k–200k ops/s on modest hardware. On a `cache.r6g.large` (current AWS instance type for session Redis), this is well within limits. At 10× we add a replica or provision a dedicated `cache.r6g.xlarge` — a config change, not a refactor.

4. **Consumer groups with at-least-once semantics.** Redis consumer groups track per-consumer delivery via the PEL. If a consumer crashes before acknowledging, the unacknowledged messages remain in the PEL and are re-claimed by another consumer. This satisfies the at-least-once requirement for billing events. Combined with idempotent processing on the consumer side (idempotency key on events), we get exactly-once delivery to external systems without relying on the queue for the guarantee.

5. **Natural fit for future WebSocket push.** In Q2 we plan to add real-time WebSocket notifications. Redis Pub/Sub is a well-known pattern for fanning events to WebSocket servers — the same Redis instance can bridge async workers and WebSocket handlers without additional middleware.

6. **Lower operational burden for a 6-person team.** Kafka's operational surface includes: KRaft (or ZooKeeper) quorum, broker configuration (replication factor, min.insync.replicas, log compaction, retention sizing), partition rebalancing, monitoring (JMX, consumer lag, ISR state), and OS tuning (page cache, disk I/O scheduler). Redis Streams is `XADD` → `XREADGROUP` — the operational model is already known.

### Negative

1. **Memory-bound retention.** Redis stores data in RAM. We cannot retain a large backlog of old messages the way Kafka can. Mitigations:
   - Short TTL on notifications (e.g., 7 days) — a single `XTRIM` or `EXPIRE` on the stream.
   - AOF persistence on the Redis instance — durable but still RAM-backed.
   - At 10× growth, stream memory may approach 4–6 GB for a week's backlog. A `cache.r6g.xlarge` (26 GB RAM) handles this comfortably.

2. **Manual partition management.** Redis Streams does not auto-balance across shards the way Kafka partitions distribute load. At 5,000 req/s peak, a single stream with a pool of consumers is sufficient. If we need to scale further, we must shard the stream by notification type (billing stream, task stream, comment stream) — application-level logic, not automatic.

3. **No built-in dead-letter queue.** Redis Streams has no native DLQ mechanism. Failed messages remain in the PEL indefinitely until acknowledged or claimed. We must:
   - Set a `MAXDELIVERY` counter (via consumer metadata) and XADD failed messages to a separate `dead-letter` stream after N retries.
   - Alert on dead-letter stream length via existing Redis monitor.

4. **No native replay based on offset.** Consumers can read from any stream ID, so replay is possible, but there is no offset-reset policy (earliest/latest) like Kafka. This is a minor ergonomic gap, not a blocker — our consumers use `>` (deliver new) and fall back to `$` on error.

5. **Consumer rebalancing is primitive.** If a consumer in a group disconnects, its unacknowledged messages are not auto-reassigned until the next `XCLAIM` cycle. We must implement a background claimer daemon (or periodic task) that claims PEL entries older than a threshold. This is ~50 lines of code, but it's code Kafka provides for free.

6. **Checklist of Kafka-level features we forfeit:**
   - No exactly-once semantics from the broker (Kafka's idempotent producer + transactions). True exactly-once against external APIs (email, webhook) requires idempotent consumers anyway, so this matters less.
   - No Kafka Connect ecosystem. If we later migrate to microservices, the connector model would simplify data plumbing. For a monolith with a single consumer, this is irrelevant.
   - No compaction (for keyed state). Not needed for an event queue.

---

## Alternatives Considered

### Apache Kafka

**Summary:** Rejected.

**Arguments for Kafka:**
- True partition-based parallelism with automatic rebalancing — horizontally scalable by adding partitions.
- Persistent on-disk commit log — configurable retention (weeks, months) without RAM pressure.
- Idempotent producer (since 0.11) provides exactly-once semantics from producer to broker.
- Consumer groups with automatic offset commits and offset-reset policies.
- Kafka Connect for building connectors to external systems.
- Mature in the industry — proven at much larger scale.

**Why rejected, given our constraints:**

| Constraint | Kafka's Problem |
|---|---|
| **Team of 6, no Kafka experience** | Kafka's learning curve is weeks, not days. Operating a multi-broker cluster (leader election, ISR management, partition rebalancing, JMX monitoring, disk sizing) is a dedicated-role skill. Every mistake — unclean leader election, misconfigured retention, consumer group rebalance storms — is a production incident. |
| **Must deliver value in ≤2 weeks** | Setting up Kafka (KRaft or ZooKeeper) on AWS takes 3–5 days just for a production-ready cluster. Writing and testing the producer/consumer with Kafka's client API takes another week. With no prior experience, the 2-week target is unrealistic. Redis Streams achieves parity in days. |
| **No dedicated infra engineer** | Kafka demands constant vigilance: broker disk usage, consumer lag, thread counts, GC tuning, partition counts. For a team of 6 building product features, this is a tax paid weekly. Redis Streams on ElastiCache is managed — we handle the data model, AWS handles the failover. |
| **Modest budget** | A minimum Kafka deployment on AWS: 3 brokers (even with KRaft) and 1 monitoring VM. ElastiCache Serverless or a `cache.r6g.large` for streams is a fraction of the cost — we already pay for it. |
| **Current traffic is modest (500 req/s, 2M tasks/month)** | Kafka is designed for millions of events per second. At our scale (even at 10×), we pay the complexity cost without needing the throughput. |
| **No Kafka Connect need** | We have one consumer — a Python worker inside the monolith. We are not building a microservice mesh that needs Schema Registry, Kafka Connect sinks/sources, or ksqlDB. These are Kafka's core value propositions; we cannot use them. |

Kafka is the right choice for a system handling 1M+ events/s with dozens of consumers, strict ordering across partitions, and a dedicated infrastructure team. For a 6-person SaaS team at 500 req/s, it is over-engineered — the operational complexity outruns the benefits.

### Continue with synchronous dispatch + Celery

**Summary:** Rejected.

Celery with Redis as the broker would add a task queue and retry mechanism without Kafka's complexity. However:
- Celery introduces its own operational surface (worker pool management, task routing, result backends) without the architectural clarity of a stream.
- Celery's Redis broker uses lists (blocking pop) or Pub/Sub — not streams. We lose consumer groups, PEL, and the ability to replay or audit the event log.
- The team would need to learn Celery's configuration surface (queues, routing keys, rate limits, soft/hard time limits, task serialization).
- Celery's at-least-once delivery with Redis broker is less reliable than Redis Streams consumer groups (which have explicit acknowledgment).
- Redis Streams gives us a reified event log that can also feed the future WebSocket subsystem — Celery would require a separate publish channel.

Celery solves the sync-to-async problem but doesn't provide the auditability, replay, and fan-out that Streams does. If we're learning a new abstraction anyway, Streams is the better long-term foundation.

---

## Implementation Outline

1. **Week 1** — Add stream write in the Flask request handler (`XADD`). Deploy a Python consumer process that reads from the stream (`XREADGROUP`), dispatches emails/webhooks, and acknowledges (`XACK`). Start with at-least-once delivery and idempotency keys for billing events.

2. **Week 2** — Implement retry logic (backoff via `XCLAIM` with visibility timeout), dead-letter stream, and monitoring (alert on dead-letter stream length, stream lag via `XLEN`).

3. **Q2** — Add WebSocket broadcaster that reads from the same stream (or a dedicated Pub/Sub channel) and pushes notifications to connected browser clients.

---

## References

- Redis Streams documentation: https://redis.io/docs/data-types/streams/
- Redis Streams consumer groups (XREADGROUP, XACK, XCLAIM): https://redis.io/commands/xreadgroup/
- Kafka exactly-once semantics: https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/
- Redis Streams vs Kafka comparison (Confluent blog): https://www.confluent.io/blog/kafka-vs-redis/
