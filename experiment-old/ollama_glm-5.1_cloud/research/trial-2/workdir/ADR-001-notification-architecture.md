# ADR 001 — Notification Subsystem Message Broker

- **Status**: Proposed
- **Date**: 2026-05-30
- **Deciders**: Platform team (3 senior, 3 mid-level engineers)

## Context

The notification module sends emails and webhooks on task events (update, assign, complete). It runs synchronously inside the HTTP request cycle on a Python/Flask monolith serving 85K MAU (~2M tasks/month, ~500 req/s peak). This causes four production problems:

1. **Request timeouts** — notification delivery blocks responses; average latency 800 ms, spikes to 8 s during peak hours.
2. **Silent failures** — downstream provider outages drop notifications with no retry or dead-letter queue.
3. **Cascading failures** — two incidents this year where slow webhook endpoints exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") have no at-least-once or exactly-once assurance.

The system must decouple notification production from the HTTP cycle, support retry with exponential backoff, guarantee at-least-once delivery (with exactly-once processing for billing events), and handle 10× traffic growth (~5,000 req/s peak) without re-architecting. Real-time WebSocket push is planned within two quarters.

**Hard constraints**: 6-person team with no dedicated infrastructure engineer, no Apache Kafka experience, a 2-week window to deliver first value, and a budget that cannot accommodate managed Confluent Cloud at production scale.

**Existing infrastructure**: Redis is already in production handling sessions and rate limiting. PostgreSQL is the primary data store.

## Decision

> We will use **Redis Streams** as the message broker for the notification subsystem.

Billing-critical notifications will achieve exactly-once processing through application-level idempotency keys stored in PostgreSQL — not through broker-level transaction semantics. A dedicated Redis instance (separate from the session/rate-limiting instance) will host notification streams to isolate blast radius and allow independent scaling.

## Rationale

### Throughput matches the requirement with margin

Current peak is 500 req/s; the 10× growth target is 5,000 notifications/s. A single Redis instance processes 100K+ simple commands/s on modern hardware. Even accounting for stream-specific overhead and payload sizes (~1 KB per notification), a single instance covers the target with 20× headroom. Kafka's advantage at millions of messages per second is irrelevant at this scale.

### The team can operate it

Redis is already in our stack. The team has operational experience with it — monitoring, upgrades, persistence configuration, failover with Redis Sentinel. Kafka introduces an entirely new operational surface: broker clusters, partition management, consumer lag monitoring, ZooKeeper/KRaft coordination. With no dedicated infrastructure engineer and zero Kafka experience on the team, the operational risk is disproportionate to the throughput requirement.

### Time-to-value fits the constraint

Redis Streams require adding `XADD` calls to the notification producer and a worker loop using `XREADGROUP` with `XACK`. A minimal viable consumer group and retry mechanism can be in production in under a week. Kafka requires cluster provisioning, topic/partition design, security configuration, monitoring setup, and team ramp-up — well beyond the 2-week value-delivery window.

### Ordering and consumer groups are sufficient

Redis Streams guarantee per-stream ordering via millisecond-precision timestamps and monotonically increasing IDs. For notifications, where events are partitioned by stream key (e.g., `notifications:billing`, `notifications:webhook`), this provides the same ordering guarantee as Kafka's per-partition ordering. Consumer groups (`XGROUP`, `XREADGROUP`) support fan-out consumption with pending-entry lists (PEL) for claiming unacknowledged messages — the primitive needed for retry with exponential backoff.

### Exactly-once is application-level regardless of broker

Kafka's exactly-once semantics (idempotent producers + transactional consumers) guarantee exactly-once *delivery* to the broker consumer offset. They do not guarantee exactly-once *processing* at the application level — a consumer that crashes after sending an email but before committing the offset will retry, producing a duplicate notification. The standard pattern, regardless of broker, is idempotent processing using a unique key persisted in the application's database. For billing notifications, we will write an idempotency key (e.g., `billing:{event_type}:{entity_id}`) to PostgreSQL before sending the notification, and check it on every processing attempt. This achieves exactly-once processing without relying on broker transaction semantics — and it works identically in Redis Streams and Kafka.

### Budget and infrastructure cost

Redis Streams add negligible incremental cost: one additional Redis instance (~$50–100/month on AWS for a memory-optimized instance at current scale). Kafka requires a minimum 3-broker cluster for production redundancy, plus monitoring infrastructure — at least $300–500/month self-hosted, or significantly more as a managed service. Confluent Cloud is explicitly out of budget.

### WebSocket push alignment

Redis Pub/Sub is a natural complement to Streams for real-time WebSocket fan-out: notifications are persisted to a stream for reliable processing, and a Pub/Sub channel fans out live updates to connected WebSocket servers. This is a common pattern (stream for durability, pub/sub for liveness) and both run on the same Redis instance. Kafka would serve the durable side but requires a separate mechanism for the low-latency fan-out.

## Alternatives Considered

- **Apache Kafka** — Rejected because the team has no Kafka operational experience, the 2-week value-delivery window does not accommodate the learning curve and cluster setup, and the budget cannot support managed Kafka. Kafka's strengths — multi-consumer replay from arbitrary offsets, partition-based horizontal scaling to millions of messages/s, and long-term log retention — solve problems we do not currently have. **We would choose Kafka instead if**: throughput requirements exceeded 50K msg/s, we needed durable event replay across multiple independent consumer services, we had a dedicated infrastructure engineer, or we had budget for a managed Kafka service.

- **PostgreSQL LISTEN/NOTIFY + queue tables** — Rejected because LISTEN/NOTIFY is fire-and-forget (no persistence, no consumer groups, no retry); polling a queue table adds write-amplification under load. This approach re-introduces the same coupling problems at the database layer and does not support fan-out to multiple consumer groups.

- **RabbitMQ** — Not evaluated in depth. Adequate throughput and supports retry/dead-letter queues, but introduces a new operational component (no team experience, no existing deployment) without providing significantly more than Redis Streams for our use case. The 2-week constraint again disqualifies it.

## Consequences

- **Positive**
  - Delivers value within the 2-week window — producers can emit `XADD` and workers can consume `XREADGROUP` in days, not weeks.
  - No new operational component; team already monitors Redis and can apply existing runbooks to the notification Redis instance.
  - Single-digit monthly cost increase at current scale; no per-message pricing model.
  - Consumer groups with pending-entry lists provide the retry/backoff primitive natively (unacknowledged messages are claimable by another consumer after a timeout).
  - Redis Pub/Sub co-exists on the same instance for WebSocket push, avoiding a second new system.
  - Scales to the 10× traffic target (~5,000 msg/s) with 20× headroom on a single instance; sharding by stream key or adding a second instance covers further growth.

- **Negative**
  - Redis Streams lack built-in dead-letter queue routing. We must implement DLQ logic in the worker (move messages to a separate stream after N retry failures). This is straightforward but requires custom code.
  - Redis persistence is asynchronous by default (AOF with `everysec` policy). Under a catastrophic Redis crash, up to 1 second of messages may be lost. For billing notifications, we mitigate this by writing the notification event to PostgreSQL *before* `XADD`, making Redis the delivery queue and PostgreSQL the source of truth.
  - Redis Streams do not support partitioned consumption across keys within a single consumer group in the same way Kafka does. Horizontal scaling means distributing stream keys across instances. This is acceptable at our scale but becomes operationally complex if we exceed ~50K msg/s in the future.
  - The operational skill gap in Kafka is deferred, not eliminated. If the platform grows to require multi-service event sourcing, Kafka (or a similar log-based system) will need to be introduced, and the ramp-up cost will still apply at that point.

- **Follow-ups**
  1. Provision a dedicated Redis instance for notifications (separate from session/rate-limit Redis) with AOF persistence and Sentinel-based failover.
  2. Implement the idempotency-key check in the notification worker for all billing event types before sending.
  3. Define stream key structure: `notifications:{type}` (e.g., `notifications:billing`, `notifications:email`, `notifications:webhook`).
  4. Implement DLQ worker: after 5 retries with exponential backoff, move messages to `notifications:dead-letter:{type}` and alert.
  5. Add Redis Stream consumer-lag and DLQ depth metrics to the monitoring dashboard.
  6. Revisit this decision when sustained notification throughput exceeds 20,000 msg/s or when multi-service event replay becomes a requirement.