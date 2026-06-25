# ADR 0001 — Notification Subsystem: Redis Streams over Apache Kafka

- **Status**: Proposed
- **Date**: 2026-06-25
- **Deciders**: Engineering team (3 senior, 3 mid-level)
- **Context tags**: notification-system, messaging, redis, kafka

---

## Context

The notification module currently processes emails and webhooks synchronously inside the Flask HTTP request cycle. This has produced four distinct production failures: response latency spikes to 8s at peak, silent notification loss when downstream services are unavailable, two cascading connection-pool exhaustion incidents, and no delivery guarantee for billing-critical events. We need to migrate to an asynchronous message-processing architecture within a two-week window before the next quarterly planning cycle.

Constraints from the system overview:

- **Team**: 6 engineers (3 senior, 3 mid-level), zero dedicated infrastructure engineers, no Kafka operational experience today.
- **Existing infrastructure**: Redis is already in production for session storage and rate limiting on all four web servers.
- **Budget**: Cannot afford Confluent Cloud or other managed Kafka offerings at full-scale pricing.
- **Timeline**: Must deliver initial value within two weeks; cannot absorb a multi-week Kafka cluster provisioning and team upskilling cycle.
- **Scale target**: 500 req/s peak (current); must accommodate 10× growth (5,000 req/s) without re-architecting.
- **Delivery guarantee**: Billing notifications (trial expiry, payment failure) require exactly-once semantics. All other notifications require at-least-once.

---

## Decision

> We will use Redis Streams as the message transport for the notification subsystem.

The Flask application will produce notification events to a Redis Stream on every relevant task event (create, update, assign, complete). A pool of Python worker processes — co-located on the existing web servers or on dedicated sidecar containers — will consume events via consumer groups, execute delivery (email via SMTP, webhook via HTTP), and acknowledge processing. Failed deliveries will be requeued with exponential backoff via a sorted-set-based retry schedule. Exactly-once semantics for billing events will be achieved by writing a deduplication entry (event ID → delivered timestamp) to PostgreSQL before processing and checking it before each delivery attempt.

---

## Rationale

### Why Redis Streams fits this team and constraint set

**Operational continuity.** The team already operates Redis in production. No new server provisioning, no new port exposures, no new secrets to rotate. The operational surface area does not expand.

**Time-to-value under two weeks.** Redis Streams shares the same client library (`redis-py`) and mental model (key-value with new data structures) that the team already uses for session storage. A minimal producer → stream → consumer-group → XACK pipeline can be running in under five days, including retry logic and a dead-letter tracker. Kafka requires choosing a deployment topology (self-managed brokers, or a managed offering), configuring ZooKeeper/KRaft, designing partition counts and replication factors, learning the offset-management model, and building consumer group rebalance handling. That learning curve alone exceeds two weeks for a team with no prior experience.

**Sufficient throughput for 10× growth.** The current peak is 500 req/s. A single Redis instance (even on a modest AWS `t3.medium`) comfortably handles 50,000–100,000 commands per second for a stream workload. Our stream traffic (event write + consumer ACK + retry schedule write) is at most 3–5 ops per notification, meaning a single Redis node supports 10,000–15,000 notification events per second — covering the 10× growth target of 5,000 req/s before any sharding is required. Kafka's per-partition throughput is higher (MB/s rather than ops/s), but that margin is irrelevant at our scale.

**At-least-once delivery is native.** Redis Streams with consumer groups provides automatic redelivery of unacknowledged messages after the consumer's claim window expires (`BLOCK` timeout + `XREADGROUP`). Workers `XACK` only after confirmed delivery (HTTP 2xx or SMTP success), so crashes before acknowledgment result in automatic redelivery. This directly satisfies the at-least-once requirement without any custom logic.

**Exactly-once for billing via idempotency layer.** Redis Streams guarantees at-least-once per consumer group, but not exactly-once across producers or across process restarts. To close this gap for billing events, we will write a PostgreSQL row with `(event_id, delivered_at)` before each delivery attempt and `SELECT ... FOR UPDATE` to check for an existing delivery before reprocessing. The stream entry ID (`<timestamp>-<sequence>`) serves as a globally unique event ID. This is a thin, well-understood pattern that requires no new infrastructure.

**Retry with exponential backoff.** A Redis sorted set (`notifications:retry`) keyed by next-retry timestamp will be written by workers on transient failure (5xx from webhook/SMTP). A scheduler loop will `ZRANGEBYSCORE` for due entries and republish them to the stream. This is 15–20 lines of Python and requires no additional Redis capabilities.

**Ordering guarantee.** Redis Streams maintains insertion order within a single stream. Consumer groups preserve per-consumer ordering. For webhook and email delivery, ordering matters only within a single notification type per entity (e.g., all task-update events for task #123 arrive in order to the same consumer), which is satisfied by routing by `entity_id % consumer_count` to a named consumer within the group.

**No operational complexity beyond Redis.** Kafka requires monitoring broker health, partition leadership, consumer group lag, replication lag, disk utilization per partition, and schema registry if Avro is used. Redis Streams requires monitoring stream length, consumer group lag (`XPENDING`), and memory usage — all visible via `redis-cli INFO` and the existing Redis monitoring stack.

---

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for high-throughput distributed messaging and would be the correct choice at higher scale. It offers:

- **Native exactly-once semantics** (EOS) via transactional producers and consumers, which would satisfy the billing notification requirement without a PostgreSQL deduplication table.
- **Multi-system fan-out**: a single Kafka topic can feed email workers, webhook workers, WebSocket push workers, and an analytics pipeline simultaneously with zero additional producer-side cost.
- **Durable log retention**: messages are retained on disk for a configurable period (e.g., 7 days), enabling replay without a dead-letter queue.
- **Throughput headroom**: a 3-broker Kafka cluster comfortably handles hundreds of thousands of messages per second, well beyond our 5,000 req/s target.

Kafka was rejected for this decision because:

1. **Operational burden is disproportionate to current scale.** A production Kafka cluster (even a 3-broker single-AZ setup) requires managing ZooKeeper or KRaft quorum, configuring `min.insync.replicas`, designing partition counts to avoid hot spots, and handling broker failures gracefully. For a team with no Kafka experience and no dedicated infrastructure engineer, this is a multi-month investment before the system is production-ready.
2. **Two-week delivery is not achievable.** Provisioning brokers, configuring replication, building the producer/consumer pipeline with correct offset management, and implementing graceful rebalancing handling cannot be done safely in two weeks. The notification subsystem must deliver value (decoupling, retry, basic delivery) within that window.
3. **Budget constraint rules out managed Kafka.** Confluent Cloud, AWS MSK, and Redpanda Cloud all price on data transfer volume and broker count. At 2M tasks/month producing ~8M notification events/month, plus retry traffic, the monthly Kafka infrastructure cost would be $400–$1,200/month — significant for a modest budget. Redis Streams adds zero marginal infrastructure cost since Redis is already running.
4. **WebSocket fan-out can be solved incrementally.** The requirement to add WebSocket push notifications within two quarters does not require Kafka's fan-out capability. A separate Redis Pub/Sub channel or a dedicated WebSocket worker consuming from the same Redis Stream can accomplish this without Kafka's complexity.

**We would choose Kafka** if the throughput target were above 50,000 events/second, the team size were 15+ with a dedicated platform/infrastructure engineer, the budget allowed $1,000+/month for managed Kafka, or the system required multi下游 fan-out to more than five independent consumers.

---

## Consequences

### Positive

- Notifications are fully decoupled from the HTTP request cycle. Flask handlers write to Redis and return immediately (single-digit millisecond overhead); workers handle delivery asynchronously.
- Transient failures (SMTP 4xx, webhook 5xx) trigger automatic retry with exponential backoff via the sorted-set scheduler, eliminating silent drops.
- Cascading failures are contained: a slow webhook endpoint causes the worker pool to saturate its retry queue, not the Flask connection pool.
- Billing notifications achieve exactly-once via the PostgreSQL idempotency table, satisfying the non-negotiable requirement.
- Redis Streams consumer group lag (`XPENDING`) provides a direct monitoring metric for stuck or slow consumers.
- The existing Redis Sentinel/Cluster setup (if any) can be reused for high availability; no new replication topology is needed.
- WebSocket push can be added as a second consumer group on the same stream with no changes to producers.

### Negative

- Redis Streams is not a durable log in the Kafka sense. Stream entries are stored in Redis memory, subject to `maxmemory` eviction policy. To maintain durability guarantees, the stream must be configured with `MAXLEN ~` trimming at a conservative cap or backed by Redis Cluster with replication. For our retention window (hours of retry backoff, not days), this is acceptable.
- Ordering across multiple consumer groups is not guaranteed. If strict total ordering of all events is required in the future, Redis Streams cannot provide it without a single-consumer constraint, which defeats horizontal scaling.
- At scale (beyond 10× growth), a single Redis instance may become a bottleneck. Readscalability is achievable via Redis Cluster (hash-slot sharding), but this requires application-side routing changes. The architecture must be revisited if the 50× growth scenario (250,000 req/s) materializes.
- Exactly-once semantics rely on a PostgreSQL round-trip per billing event. At 5,000 billing events/second, this could create hot-row contention on the idempotency table. Mitigation: batch-check dedup keys with a `WHERE event_id IN (...)` query and use `INSERT ... ON CONFLICT DO NOTHING`.
- Redis Streams lacks native dead-letter queue semantics. Unretryable messages (e.g., permanent 4xx from a validated email address) must be moved to a separate stream (`notifications:dlq`) manually by workers after a defined retry count is exceeded.

### Follow-ups

1. Implement the stream producer in the Flask application (`XADD notifications:events * entity_type task entity_id <id> event_type <type> payload <json>`).
2. Implement the consumer group worker with `XREADGROUP GROUP notifier-workers CONSUMER <hostname> COUNT 10 BLOCK 2000`.
3. Implement the retry scheduler: write to `ZADD notifications:retry <timestamp> <event_json>` on transient failure; scheduler loop republishes due entries.
4. Implement the PostgreSQL idempotency table: `CREATE TABLE notification_dedup (event_id VARCHAR(64) PRIMARY KEY, delivered_at TIMESTAMPTZ NOT NULL);`.
5. Add `XPENDING` and stream length metrics to the existing Redis monitoring dashboard.
6. Implement dead-letter stream: after N retry attempts, `XADD notifications:dlq * <original_event> failure_reason <reason> retry_count <n>`.
7. Add WebSocket push as a second consumer group on the same stream within the two-quarter window.
