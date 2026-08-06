# ADR-001: Notification Subsystem — Apache Kafka vs. Redis Streams

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users with ~2M tasks created per month and a peak of ~500 req/s during business hours. The backend is a Python/Flask monolith backed by PostgreSQL and Redis, running on 4 web servers behind nginx on AWS.

The current notification system sends emails and webhooks synchronously inside the HTTP request cycle. This has caused:

1. **Request timeouts** — average latency 800 ms, spiking to 8 s at peak.
2. **Silent failures** — no retry or dead-letter queue when providers are down.
3. **Cascading failures** — slow webhook endpoints have exhausted the DB connection pool twice this year, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") have no at-least-once or exactly-once assurance.

We must decouple notifications from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), and prepare for real-time WebSocket push within 2 quarters — all while supporting 10× traffic growth.

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Operational footprint**: Redis is already in production for sessions and rate limiting; no one on the team has Kafka experience.
- **Time-to-value**: must deliver measurable improvement within 2 weeks of starting.
- **Budget**: modest — managed Confluent Cloud at full production scale is not feasible today.
- **Correctness**: billing notifications require exactly-once delivery semantics.

### Throughput Requirements

Current peak is ~500 req/s. Not every request produces a notification; conservatively, peak notification throughput is ~1,000 messages/s. A 10× growth target means ~10,000 messages/s at the ceiling. Both Kafka and Redis Streams handle this comfortably — the differentiator is operational, not capacity.

## Decision

**We will use Redis Streams as the notification subsystem's message broker.**

Redis Streams satisfies our throughput requirements, provides consumer-group semantics for async processing, and — critically — can be rolled out by a team that already operates Redis, within the 2-week delivery window. Kafka's stronger theoretical guarantees come at an operational cost our team cannot absorb today.

### Justification

| Property | Kafka | Redis Streams | Relevance |
|---|---|---|---|
| **Throughput** | 100 K–1 M+ msg/s | 10 K–500 K msg/s | Both exceed our 10 K msg/s ceiling. Not a differentiator. |
| **Ordering guarantees** | Per-partition strict ordering | Per-stream strict FIFO ordering | Both sufficient; our notifications are independent per event type. |
| **Message retention** | Configurable days-to-weeks; designed for durable replay | Capped by `MAXLEN` or TTL; eviction is trim-from-head | Kafka wins on replay depth. We need hours of retention for retry cycles, not weeks — Redis is adequate. |
| **Consumer groups** | Native, mature, rebalancing on partition assignment | `XREADGROUP` + `XPENDING`/`XACK`; no automatic rebalancing | Redis consumer groups require application-level rebalancing. Acceptable for our scale (a handful of workers, no dynamic membership churn). |
| **Exactly-once semantics** | Idempotent producer + transactional consumer (Kafka 0.11+) | At-least-once by default; exactly-once requires application-level idempotency | We will implement idempotency keys on billing notifications regardless of broker — even Kafka transactions cover only the broker-to-consumer leg, not the consumer-to-external-service leg. Application-level deduplication is mandatory either way. |
| **Operational complexity** | High: brokers, partitions, ZooKeeper/KRaft, topic management | Low: single Redis instance/cluster we already run | This is the deciding factor. No infra engineer, no Kafka experience, 2-week deadline. |
| **Time to first value** | Weeks (new infra, new operational runbook, team ramp-up) | Days (add streams to existing Redis, write consumer workers) | |

The decisive factor is **operational fit**. A 6-person team without a dedicated infra engineer and with zero Kafka experience cannot safely operate a Kafka cluster under production load within 2 weeks. Redis Streams let us ship a working async notification pipeline in days, on infrastructure we already monitor and understand.

## Consequences

### Pros

- **Fast delivery**. We can ship a working notification worker reading from Redis Streams within the first sprint, immediately eliminating synchronous blocking and request timeouts.
- **No new infrastructure**. Redis is already in production with monitoring, alerting, and on-call runbooks. Adding streams is a configuration change, not a deployment.
- **Consumer groups work**. `XREADGROUP` gives us per-consumer delivery, pending-entry tracking, and acknowledgement — the primitives needed for retry with exponential backoff and dead-letter routing.
- **At-least-once by default**. Unacknowledged messages remain in the pending list and are claimable by another consumer, satisfying our delivery-guarantee requirement.
- **WebSocket path is natural**. Redis Pub/Sub (which we can enable on the same instance) is the standard pairing for real-time push to connected WebSocket servers, keeping the infrastructure footprint flat.
- **10× headroom**. Redis Streams handle well beyond our projected 10,000 msg/s on current hardware.

### Cons

- **Exactly-once requires application code**. Redis Streams provide at-least-once; exactly-once for billing notifications means we must implement idempotency keys (e.g., `notification_id` deduplication table in PostgreSQL). This is extra work, but it is work we would need under Kafka as well — Kafka transactions do not guarantee exactly-once delivery to an external email/webhook endpoint.
- **Limited replay window**. Message retention is bounded by `MAXLEN` or max memory. We cannot replay weeks of history. For our use case (retry cycles measured in minutes to hours, not days), this is acceptable. We will set `MAXLEN` to retain ~24 hours of messages and archive critical billing events to PostgreSQL before trimming.
- **No automatic consumer rebalancing**. If a worker dies, another must claim its pending messages via `XPENDING` + `XCLAIM`. We will implement this in the worker library; it is straightforward at our consumer count (< 10 workers).
- **Durability depends on Redis persistence config**. AOF or RDB must be enabled and tuned. Our production Redis already runs with AOF; we will verify `appendfsync everysec` is set and add a persistence alert to the runbook.
- **Future scale ceiling**. If notification volume grows beyond ~100 K msg/s or we need multi-data-center replication, Redis Streams will require re-evaluation. At that point, the team will have the operational maturity and headcount to consider Kafka. This is a deliberate "use it until it breaks" trade-off.

## Alternatives Considered

### Apache Kafka

Kafka is the stronger broker in isolation: durable log, long retention, mature consumer groups with automatic rebalancing, and exactly-once semantics at the broker level. We rejected it for this phase because:

1. **Operational overhead is disproportionate.** Running Kafka production-grade (replication factor ≥ 3, monitoring partition lag, handling broker failures, ZooKeeper or KRaft lifecycle) requires dedicated infrastructure expertise we do not have. A misconfigured Kafka cluster is worse than no broker — it creates silent data loss and hard-to-diagnose latency spikes.

2. **2-week delivery constraint is infeasible.** Even with managed Confluent Cloud, the team must learn Kafka's data model (topics, partitions, consumer groups, offsets), write new client code, and build operational runbooks. This pushes the first measurable improvement past the deadline.

3. **Budget rules out managed Kafka at scale.** Confluent Cloud's pricing at our throughput is not sustainable on the current budget. Self-managed Kafka on EC2 shifts the cost to engineering time, which is the scarcer resource.

4. **Exactly-once still needs application-level work.** Kafka's transactional consumer guarantees exactly-once consumption from the topic, but our notifications terminate at external services (SendGrid, customer webhook endpoints). The final delivery leg — the HTTP call and its result — requires idempotency keys regardless. Kafka does not eliminate the application-level deduplication we must build for billing notifications.

**We may revisit Kafka if/when**: the team grows to include a dedicated platform engineer, notification volume exceeds 100 K msg/s, or we need multi-region log replication. At that point, migrating from Redis Streams to Kafka is a well-understood path: the consumer-group and retry semantics we build now translate directly.