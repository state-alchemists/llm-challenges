# ADR-001: Notification Subsystem — Async Event Broker

**Status:** Proposed

---

## Context

The Notifier subsystem runs synchronously inside the Flask HTTP request cycle. This coupling causes four interconnected failures:

1. **Request timeouts** — sending email and webhook notifications blocks the response. Average latency is 800 ms, spiking to 8 s during peak hours.
2. **Silent failures** — a dead email provider or unreachable webhook endpoint drops the notification with no retry or dead-letter queue.
3. **Cascading failures** — slow webhook endpoints exhaust the database connection pool (two incidents this year), taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications (trial expiry, payment failure) must be delivered exactly once, but the current system offers no such guarantee.

We need to decouple notification production from consumption — an async event broker in the middle. The broker must support retry with exponential backoff, at-least-once delivery (exactly-once where feasible), and handle 10× traffic growth without re-architecting. Real-time WebSocket push is on the roadmap within two quarters.

**Constraints:**

| Constraint | Detail |
|---|---|
| Team size | 6 engineers (3 senior, 3 mid). No dedicated infrastructure engineer. |
| Existing infrastructure | Redis already in production (session storage, rate limiting). No Kafka. |
| Team experience | Zero Kafka experience. Solid Python/Redis familiarity. |
| Delivery window | Must ship value within 2 weeks; cannot afford a multi-month migration. |
| Budget | Modest — managed Confluent Cloud is out of reach at full scale. |
| Exactly-once | Required for billing notifications. |

---

## Decision

**Adopt Redis Streams as the notification event broker.**

Redis Streams — specifically its consumer group protocol (`XADD` / `XREADGROUP` / `XACK`) — will sit between the Flask request handlers and the notification workers. The request handler writes a notification event to the appropriate stream and returns immediately. A pool of background workers (running in separate processes or containers) consumes from the stream, sends the email or webhook, and acknowledges the message.

**Key configuration:**

- One stream per notification category: `notify:email`, `notify:webhook`, `notify:billing`.
- Streams capped with `MAXLEN ~ 100000` to bound memory usage.
- Consumer groups with 3–5 workers per stream for horizontal scaling.
- AOF persistence + Redis replication for durability.
- Idempotent consumers for billing streams: deduplicate via a `processed_notifications` table in PostgreSQL keyed on `(notification_id)`.

---

## Consequences

### Pros

1. **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. Adding Streams costs nothing in operational surface area. We don't need to learn, deploy, or troubleshoot a JVM cluster.

2. **Fast time-to-value.** `XADD` in the request handler and `XREADGROUP` in a worker is a ~3-day implementation. The 2-week delivery window is comfortably met.

3. **Team-fit operational complexity.** Consumer groups, pending-entry lists (`XPENDING`), and auto-claim (`XAUTOCLAIM`) are Redis commands, not a separate platform. Any mid-level engineer on the team can develop against and debug them. No dedicated infrastructure engineer required.

4. **Throughput headroom.** Redis Streams handles ~100K messages per second per stream (source: OneUptime comparison, 2026). Current peak is ~500 req/s. Even at 10× traffic (5,000 req/s), we operate at 5% of capacity — 20× headroom per stream.

5. **Sub-millisecond producer latency.** `XADD` completes in <1 ms on a local Redis instance, so the Flask handler is never blocked longer than a memory write. This directly solves the request-timeout and connection-pool-exhaustion problems.

6. **Natural WebSocket path.** Redis Pub/Sub (separate from Streams, but same instance) can push events to WebSocket servers for real-time UI updates — the roadmap item we need in two quarters.

7. **At-least-once delivery.** Consumer groups require explicit `XACK`. If a worker crashes before acknowledging, the message remains in the Pending Entry List (PEL) and is reassigned via `XAUTOCLAIM`. No silent drops.

8. **Retry and dead-letter queue.** A worker that fails after N retries `XADD`s the message to a `notify:dlq` stream with error metadata, then `XACK`s the original. A separate process monitors the DLQ and alerts on thresholds.

### Cons

1. **Exactly-once requires application-level idempotency.** Redis Streams does not provide native exactly-once semantics (no transaction coordinator, no idempotent producer). For billing notifications, we must implement idempotent consumers: store `notification_id` in PostgreSQL with a unique constraint before acting, and skip on conflict. This is well-understood and standard practice, but it is extra implementation work.

    KAFKA's exactly-once semantics (idempotent producer + transactions) only guarantee exactly-once *within the Kafka cluster*. Delivering to an external API — email provider, Stripe webhook — still requires idempotent consumers on the other end, because the external system can fail after processing but before Kafka receives the commit. In practice, both options require application-level idempotency for external delivery; Kafka's guarantee only covers the broker-internal pathway.

2. **Retention is memory-bound.** Redis operates primarily in memory. `MAXLEN ~ 100000` per stream keeps memory predictable, but we cannot retain months of event history in the stream itself. If long-term audit trails are needed, we must archive processed events to S3 or PostgreSQL separately. This is a one-time job per stream, not an ongoing operational burden.

3. **Total order within a stream, not across streams.** Redis Streams guarantees global ordering within a single stream key, but not across streams. If cross-stream ordering ever becomes a requirement (e.g., "all events for task X arrive in order regardless of type"), we would need a single stream with a type discriminator field. This is a schema design decision, not a technical blocker.

4. **Single-threaded bottleneck under write contention.** Redis processes commands on a single thread. At extreme throughput (>100K msg/s), a heavily-written stream could contend with session and rate-limiting operations. At our projected 5,000 req/s peak, this is not a concern. If it becomes one, we can move notification streams to a dedicated Redis replica with `REPLICAOF`.

5. **No managed schema evolution.** Redis Streams has no schema registry (unlike Kafka + Confluent Schema Registry). Message format changes require coordinated producer/consumer deploys or a version field in the message body. For a 6-person team, this is manageable with documentation and a brief grace period during deploys.

---

## Alternatives Considered

### Apache Kafka (rejected)

**Why it was evaluated:** Kafka is the industry standard for event streaming. It offers exactly-once semantics, disk-persisted log retention, multi-partition fan-out, and a mature ecosystem (Kafka Connect, Schema Registry, Kafka Streams, ksqlDB).

**Why it was rejected:**

1. **Operational complexity exceeds team capacity.** Running Kafka in production requires either:
   - A ZooKeeper ensemble (legacy) or KRaft quorum (Kafka 3.x+)
   - Broker tuning for page cache, disk I/O, replication, and rebalancing
   - Dedicated monitoring for consumer lag, partition leadership, ISR state
   
   With 6 engineers, no dedicated infrastructure role, and no Kafka experience on the team, operating a Kafka cluster is a net-negative. The learning curve alone would consume the 2-week delivery window before a single message flows.

2. **Managed Kafka is unaffordable.** Confluent Cloud pricing for sustained 500 msg/s would cost thousands per month at full scale. AWS MSK reduces operational burden but still requires broker management and costs significantly more than an ElastiCache Redis node. Budget is constrained.

3. **Overkill for the current scale.** Kafka excels at millions of messages per second, multi-TB retention, and cross-team event buses with dozens of independent consumers. Our notification subsystem has <10 consumer groups (email, webhook, billing, future WebSocket) operating at ~500 msg/s. Redis Streams meets every functional requirement at this scale with a fraction of the complexity.

4. **Does not solve the external exactly-once problem.** Kafka's native exactly-once semantics only apply within the Kafka cluster. Delivering a notification to an external email API or webhook endpoint still requires an idempotent consumer — the same pattern Redis Streams demands. Kafka adds no advantage for the specific constraint ("billing notifications must be delivered exactly once") that Redis Streams cannot match with an idempotency table.

5. **JVM resource footprint.** Kafka runs on the JVM. A three-broker production cluster requires 8–16 GB of heap per broker, plus page cache. The same notification workload on Redis Streams runs comfortably on a 4 GB ElastiCache node, which we already have provisioned for session storage.

**When to reconsider:** If the notification subsystem grows into a company-wide event bus serving 10+ independent consumer groups across multiple teams, or if throughput exceeds 100K msg/s, Kafka becomes the right choice. At that point, the team will also have grown enough to justify dedicated infrastructure support.

### Redis Pub/Sub (considered, rejected independently of scope)

Redis Pub/Sub was not formally evaluated as an alternative because it is fire-and-forget: messages are lost if no consumer is listening. This fails the at-least-once delivery requirement and the retry requirement. Redis Streams is the correct Redis-native primitive for this use case.

---

## Implementation Plan (Summary)

| Phase | Duration | Deliverables |
|---|---|---|
| 1. Stream producer | Week 1 | Replace synchronous `send_email()` / `send_webhook()` with `XADD` calls in request handlers. One stream per category. |
| 2. Stream consumers | Week 1–2 | Background worker process with `XREADGROUP`, retry logic, `XAUTOCLAIM`, and DLQ. |
| 3. Idempotency | Week 2 | Dedup table in PostgreSQL for billing streams. |
| 4. Monitoring | Week 2 | Prometheus metrics: stream length, consumer lag, DLQ size, retry counts. Alerts on DLQ growth. |
| 5. WebSocket (future) | Q2 | Redis Pub/Sub for live UI push on task updates. |
