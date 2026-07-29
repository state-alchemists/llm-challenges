# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

---

## Context

The Notifier subsystem of our SaaS project management platform handles email and webhook delivery when tasks are updated, assigned, or completed. Current metrics: 85k MAU, ~2M tasks/month, peak ~500 req/s.

The problem is that notifications are sent synchronously inside the HTTP request cycle (Python/Flask monolith, ~50k LOC). This causes four interrelated issues:

1. **Request timeouts** — average response latency 800ms, spikes to 8s during peak, because the response waits for email/webhook delivery to complete.
2. **Silent failures** — downstream email providers and webhook endpoints fail; the notification is dropped without retry or dead-letter tracking.
3. **Cascading failures** — two incidents this year where a slow webhook caused connection pool exhaustion, taking down unrelated features (task creation, auth, etc.).
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") have at-most-once semantics today, which is unacceptable.

### Scaling Target

- Decouple notifications from the HTTP request cycle (async processing).
- Retry with exponential backoff on transient failures.
- At-least-once delivery for all notifications; exactly-once for billing events.
- Real-time WebSocket push within 2 quarters.
- Handle 10× traffic growth (~5k req/s peak) without re-architecting.

### Constraints

| Constraint | Detail |
|---|---|
| Team size | 6 engineers (3 senior, 3 mid-level). No dedicated infra engineer. |
| Existing infra | Redis in production (session storage, rate limiting). PostgreSQL (single primary + one replica). |
| Kafka experience | None on the team. |
| Time to value | ≤2 weeks setup + migration before delivering measurable improvement. |
| Budget | Modest. Managed Confluent Cloud at full scale is unaffordable. Self-hosted Kafka commits to dedicated EC2 instances. |
| Exactly-once | Required for billing notifications. |

---

## Decision

**Use Redis Streams.**

Redis Streams will serve as the notification message broker, replacing the current synchronous delivery path. Producers (the Flask monolith) will `XADD` notification events into streams. Consumer workers (separate Python processes, scaled horizontally) will `XREADGROUP` to claim and process messages, with `XPENDING` handling retries and a separate dead-letter stream for permanently failed deliveries.

### Why Redis Streams over Kafka

Given the constraints — a 6-person team with no Kafka experience, existing Redis infrastructure, a 2-week delivery window, and modest budget — Redis Streams is the pragmatic and scalable choice. Each specific technical dimension is evaluated below.

**Throughput.** Redis Streams on modest hardware handles 100k+ messages/s for small payloads (our notifications are <10KB each). Current peak of 500 req/s — 10× that is 5k req/s — is well within Redis's envelope. Kafka can handle millions of messages/s, but that headroom is irrelevant at our projected scale.

**Consumer groups.** Both Redis Streams (`XREADGROUP`) and Kafka offer consumer group semantics: horizontal scaling with automatic partition assignment and offset tracking. Redis Streams uses a single shard per stream name but supports multiple streams for partitioning. This is simpler to reason about than Kafka's partition model and sufficient at our scale.

**Ordering guarantees.** Redis Streams guarantees FIFO ordering within a single stream, and consumers within a group process entries in order. Kafka guarantees ordering within a partition. Both models are equivalent for our use case: a single notification stream per event type preserves per-type ordering. Billing events must be ordered per customer; Redis Streams handles this with a stream per customer or a single ordered stream.

**Message retention.** Kafka's disk-based log persists messages for a configurable retention window (days/weeks, bounded only by disk). Redis Streams stores messages in memory, bounded by `maxlen`. This is the starkest trade-off. For a notification system where messages are consumed and acknowledged within minutes, memory-bound retention is acceptable: we do not need to replay two-week-old notifications. For audit trails, we write to PostgreSQL (which we already do); the stream is a dispatch mechanism, not a durable log.

**Exactly-once semantics.** Kafka provides exactly-once semantics via transactional producers and idempotent consumers. Redis Streams does not — it offers at-least-once by default. However, exactly-once for billing notifications can be achieved at the application layer using idempotency keys stored in PostgreSQL (`idempotency_key VARCHAR UNIQUE`), paired with the Redis message ID. The consumer checks the key before processing; if already processed, it acknowledges the message without action. This pattern is well-understood and gives us exactly-once semantics where it matters without depending on broker-level guarantees.

**Operational complexity.** This is the decisive dimension. Kafka requires running and tuning a JVM-based cluster (ZooKeeper or KRaft), managing partition rebalancing, monitoring broker disk/network, and handling leader elections. A 6-person team with no Kafka experience and no dedicated infra engineer would need weeks to become operational, even with managed MSK (which adds cost). Redis Streams requires no new infrastructure — we already run Redis. Introducing Streams is a client-side change (`XADD` / `XREADGROUP`) on the same Redis instance, with no new daemons, configurations, or vendor relationships.

**Time to value.** We can have a Redis Streams-based notification worker consuming from a stream in 2–3 days. Kafka would take 2+ weeks just to provision and learn the stack before writing any application code. The 2-week constraint rules Kafka out.

**Budget.** Self-hosted Kafka at 10× load requires dedicated EC2 instances (at minimum 2 brokers + ZooKeeper) and attached EBS volumes — approximately $300–600/month in AWS costs. Redis Streams uses the existing Redis instance; additional memory for stream buffers at 5k req/s is negligible (~100MB of stream data per day at 1KB/message).

### Architecture Summary

```
┌──────────┐   XADD    ┌──────────────┐   XREADGROUP   ┌──────────────────┐
│  Flask   │ ────────▶ │  Redis       │ ──────────────▶ │  Notification    │
│  Monolith│           │  Streams     │                 │  Workers (x N)   │
│          │           │              │                 │                  │
│ (Producer│           │ • notif:     │                 │ • Email sender   │
│  per req)│           │   billing    │                 │ • Webhook caller │
│          │           │ • notif:     │                 │ • WebSocket push │
│          │           │   general    │                 │  (future)        │
│          │           │ • notif:     │                 │                  │
│          │           │   dead_letter│                 │ • Idempotency    │
│          │           └──────────────┘                 │   check (PG)     │
└──────────┘                                           └──────────────────┘
                                        XPENDING/delivery_info
                                        ───────────────────▶
                                        Dead-letter after N
                                        retries
                                            │
                                            ▼
                                        ┌──────────┐
                                        │  Monitor │
                                        │  (alert) │
                                        └──────────┘
```

Key workflow:
1. Flask pushes notification payloads to the appropriate stream (`XADD`).
2. Workers claim entries via consumer groups (`XREADGROUP`). Each notification type has its own consumer group to isolate processing.
3. On failure, the worker does not `XACK`; `XPENDING` reveals unacknowledged entries. A retry scheduler re-delivers with exponential backoff.
4. After N retries (configurable per notification type, e.g. 5 for billing, 3 for general), the entry is moved to a dead-letter stream and an alert fires.
5. Billing notifications carry an idempotency key. The consumer checks `INSERT ... ON CONFLICT DO NOTHING` in PostgreSQL before processing. If the key exists, the message is acked and skipped — giving exactly-once delivery.

---

## Consequences

### Pros

- **Zero new infrastructure.** Redis is already in production for session storage and rate limiting. Streams share the same instance.
- **Rapid delivery.** A working prototype can be in production within 3–5 days; full migration within 2 weeks.
- **Team familiarity.** Every engineer knows how to connect to Redis, run `XADD`/`XREADGROUP`, and debug with `redis-cli`. No JVM, no partition tuning, no broker configuration.
- **Low operational burden.** Redis is a single process; stream management is a handful of commands. A 6-person team can own this without an infra specialist.
- **Horizontal consumer scaling.** Workers are stateless and scale via consumer groups naturally.
- **Isolation from failures.** A slow webhook endpoint no longer blocks HTTP responses or exhausts connection pools. The latency budget shifts from the request path to the async worker.
- **Natural path to WebSocket push.** A consumer group member can act as a WebSocket hub, pushing notifications to connected clients — same stream, same consumer semantics.
- **Idempotency at the database layer** gives exactly-once for billing without relying on broker-level transactions, which are harder to debug.

### Cons

- **No long-term retention.** Messages are evicted by `maxlen`. If we later need to replay notifications from days ago (e.g., rebuild a customer's audit trail from the stream), Redis Streams cannot provide it. Mitigation: notifications are already logged in PostgreSQL (for the activity feed), and billing events have their own receipt table. The stream is a dispatch mechanism, not the system of record.
- **Memory-bound throughput.** At extreme scale (100k+ req/s), Redis's single-threaded event loop and memory constraint become a bottleneck. At our projected 5k req/s peak, this is not a concern. If it becomes one, we can shard by stream name across multiple Redis instances — no architecture change, just more nodes.
- **No native exactly-once.** The at-least-once + idempotency-key pattern requires discipline: every billing consumer must implement the idempotency check. A bug in the check can produce duplicates. Mitigation: shared library function (`process_with_idempotency(message, handler)`), enforced via code review.
- **Smaller ecosystem.** Kafka has a richer tooling ecosystem (Kafka Connect, Schema Registry, ksqlDB, Confluent Control Center). Redis Streams has `redis-cli` and a handful of libraries. For a notification dispatch system with 6 engineers, the ecosystem depth is not a decisive factor.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka was seriously evaluated and rejected for three reasons that together form a hard no:

**1. Operational overhead (fatal given team size).** A production Kafka cluster at our scale requires at minimum 3 broker nodes + ZooKeeper ensemble (or KRaft), each on dedicated instances, with careful tuning of `replication.factor`, `min.insync.replicas`, log segment sizing, retention policies, and partition counts. The team of 6 with no Kafka experience would spend weeks on topology design, provisioning, and benchmarking before writing the first consumer. One incident — a partition leader rebalance gone wrong — requires JVM expertise the team does not have. Redis Streams, by contrast, uses a single command (`XGROUP CREATE`) on an existing process.

**2. Time to value exceeds the 2-week constraint.** Even with a generous estimate, provisioning a Kafka cluster, learning the client API, integrating with Flask, and migrating off the synchronous path takes 3–4 weeks for a Kafka-naive team. This is double the allowed window. Redis Streams fits comfortably within 2 weeks.

**3. Budget.** Managed Kafka (Confluent Cloud, AWS MSK) starts at $150–300/month for a minimal cluster and scales up steeply. Self-hosted Kafka requires dedicated EC2 + EBS at ~$300–600/month. Redis Streams adds zero to the existing infrastructure budget. The marginal cost of additional memory for stream buffers is negligible.

**Kafka advantages we lose:** durable disk-based retention (irrelevant — notifications are ephemeral; the audit trail lives in PostgreSQL), higher throughput ceiling (irrelevant at 5k req/s), native exactly-once (can be matched at the application layer), and richer ecosystem (not worth 2× the cost and 3× the team overhead).

### PostgreSQL LISTEN/NOTIFY (Rejected)

Considered briefly but rejected due to fundamental limitations: no consumer groups (only one listener per channel), no message persistence (lost on crash), no backpressure mechanism, no retry semantics, and a per-notification payload size limit of 8,000 bytes. This is a coordination primitive, not a message queue.

### Amazon SQS + SNS (Not selected)

Would have been a strong candidate if not for the constraint of needing to self-host the WebSocket push layer and the exactly-once requirement across database and messaging boundaries. SQS provides at-least-once; SNS fan-out works well for multi-channel delivery. However, the future WebSocket push requirement means we need a broker that worker processes can subscribe to directly, avoiding a separate pub/sub mesh. SQS's visibility timeout retry model is also less flexible than consumer-group-based message claiming. Cost at 10× scale (~500k messages/day) would be ~$20-30/month — cheap, but adds an AWS dependency where Redis already exists.
