# ADR 001 — Notification Subsystem Message Broker

- **Status**: Proposed
- **Date**: 2026-06-16
- **Deciders**: Engineering team (6: 3 senior, 3 mid-level)
- **Context tags**: notifications, async-processing, message-broker, scaling

## Context

Our SaaS project management platform (85,000 MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails and webhooks on task updates, assignments, and completions — synchronously inside the HTTP request cycle. This has caused four operational problems:

1. **Request timeouts.** Average notification latency is 800 ms; spikes reach 8 s during peak hours, blocking the response.
2. **Silent failures.** When an email provider or webhook endpoint is down, the notification is silently dropped — no retry, no dead-letter queue.
3. **Cascading failures.** Two incidents this year where a slow webhook endpoint exhausted the PostgreSQL connection pool, taking down unrelated features.
4. **No delivery guarantees.** Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once. The current system provides no such guarantee.

We must decouple notifications from the HTTP request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), and support real-time WebSocket push notifications within two quarters. The system must handle 10× traffic growth (~5,000 req/s) without re-architecting.

Key constraints:

- **Team**: 6 engineers, no dedicated infrastructure engineer, zero Kafka operational experience.
- **Time**: Value must be delivered within 2 weeks of starting migration.
- **Budget**: Modest — managed Confluent Cloud at full scale is not affordable.
- **Existing stack**: Python/Flask monolith, PostgreSQL, Redis (already used for sessions and rate limiting), 4 web servers on AWS.

## Decision

> We will use Redis Streams as the message broker for the notification subsystem.

Redis Streams (XADD, XREADGROUP, XACK, XAUTOCLAIM) provides ordered, durable, consumer-group-based message consumption on infrastructure the team already operates. We will implement application-level idempotency for billing notifications using a PostgreSQL idempotency key table, achieving effective exactly-once semantics without requiring a separate distributed system.

## Rationale

The comparison hinges on five factors that map directly to the constraints above: operational complexity, time to value, throughput headroom, exactly-once semantics, and cost.

### Throughput and ordering

Redis Streams on a single instance handle millions of operations per second. Our current peak is 500 req/s; the 10× growth target is 5,000 req/s — well within single-instance capacity. Kafka's throughput advantage (partitioned, horizontally scalable to millions of msgs/s) exceeds our needs by 2–3 orders of magnitude and comes with partition-planning complexity we do not need.

Redis Streams guarantee per-stream insertion order. Kafka guarantees per-partition order but requires a partition key strategy. For a notification system where each stream represents a logical channel (e.g., `notifications:billing`, `notifications:webhooks`, `notifications:push`), per-stream ordering is simpler and sufficient.

### Exactly-once semantics

This is the primary concern. Kafka supports exactly-once delivery via idempotent producers and transactional APIs (Kafka 0.11+), but effective exactly-once *processing* still requires the consumer to be idempotent — if a consumer crashes after processing a message but before committing its offset, the message is redelivered. The same is true for Redis Streams: XACK is issued after processing, and a crash before XACK causes redelivery.

In practice, exactly-once *delivery to the downstream system* (email provider, webhook endpoint) requires application-level idempotency regardless of the broker. We achieve this with a PostgreSQL idempotency key table: each notification carries a deterministic key (e.g., `billing:{org_id}:{event_type}:{timestamp_bucket}`), and the consumer inserts into this table with `ON CONFLICT DO NOTHING` before processing. This gives us effective exactly-once processing on both brokers; the difference is that Redis Streams requires us to build it explicitly, while Kafka requires us to build it *and* configure transactional consumers correctly.

### Operational complexity

This is the decisive factor. Kafka introduces an entirely new distributed system: 3+ brokers for production (replication factor 3), ZooKeeper or KRaft for coordination, partition management, ISR monitoring, topic configuration, and dedicated monitoring (UnderReplicatedPartitions, consumer lag). Our team has no Kafka experience and no dedicated infrastructure engineer. Self-hosted Kafka on a 6-person team with a 2-week deadline is a significant operational risk.

Redis Streams run on the Redis instance we already operate. Adding Streams means adding XADD/XREADGROUP calls to our existing Python/Redis integration — no new daemons, no new monitoring stack, no new failure modes. Our team already knows Redis.

### Time to value

Redis Streams integration can be completed within the 2-week constraint: a Flask background worker consuming from streams, a producer that XADDs instead of calling notification functions synchronously, and an idempotency table in PostgreSQL. Kafka provisioning, configuration, team training, and production hardening would take 4–8 weeks minimum for a team with no prior experience.

### Cost

We already pay for Redis. Kafka self-hosted requires 3+ EC2 instances (or EKS pods) plus storage. Managed Confluent Cloud charges per GB ingested and per partition — exceeding our modest budget at scale. Redis Streams add zero incremental infrastructure cost.

## Consequences

### Positive

- **Immediate value within the 2-week constraint.** No new infrastructure to provision, monitor, or learn. The team writes XADD in the Flask request path and XREADGROUP in a background worker — patterns already familiar from our Redis usage.
- **Simpler operational model.** One distributed system (Redis) instead of two. Redis persistence (RDB + AOF) already configured for our existing session/rate-limiting workload covers Stream durability.
- **Sufficient throughput headroom.** A single Redis instance handles our current 500 req/s peak with orders of magnitude to spare, and 10× growth (5,000 req/s) remains within single-instance capacity. Horizontal scaling via Redis Cluster is available if we eventually need it.
- **Consumer groups work for our fan-out pattern.** XGROUP and XREADGROUP provide exactly the model we need: multiple workers consuming from the same stream, automatic claim transfer on failure (XAUTOCLAIM), and pending-entry tracking for retry.
- **Lower cost.** No new infrastructure spend beyond what we already pay for Redis.

### Negative

- **No native exactly-once semantics.** We must implement application-level idempotency for billing notifications. This is a PostgreSQL idempotency key table per the Decision section — additional schema and logic, but straightforward and auditable.
- **Message retention is bounded by memory.** Redis Streams hold messages in memory (with persistence to disk via AOF/RDB). Long retention on high-volume streams increases memory pressure. We mitigate this with MAXLEN trimming (e.g., keep the last 100,000 messages per stream) and archive processed billing events to PostgreSQL before trimming.
- **No native replay from arbitrary offsets for long periods.** Kafka supports replaying days or weeks of history. Redis Streams with MAXLEN trimming lose old messages. For notifications — where processing is expected within seconds and billing events are archived to PostgreSQL — this is acceptable. If we later need long-term event replay for analytics, we will need a separate solution (e.g., a CDC pipeline from PostgreSQL).
- **Single-node Redis is a SPOF for the notification subsystem.** Our current Redis instance is already a SPOF for sessions and rate limiting, so this does not introduce new risk. Mitigation path: Redis Sentinel or Redis Cluster for HA, which we can adopt when we outgrow the single instance — and we will need it for sessions anyway, not just for Streams.
- **Smaller ecosystem for stream processing.** Kafka has Kafka Streams, ksqlDB, and extensive connector libraries. Redis Streams has none of these. Our notification processing is simple enough (consume → process → ack → retry) that a custom Python worker suffices, but if we later need complex stream joins or windowed aggregations, Redis Streams alone will not support it.

### Follow-ups

1. **Implement idempotency key table in PostgreSQL** — schema: `(key TEXT PRIMARY KEY, processed_at TIMESTAMPTZ)`. Use `INSERT ... ON CONFLICT DO NOTHING` in the billing notification consumer.
2. **Implement notification worker** — Python process using XREADGROUP to consume from `notifications:billing`, `notifications:webhooks`, `notifications:push` streams; exponential backoff via XAUTOCLAIM with `MAXDELIVERY` counter or application-level retry tracking.
3. **Implement producer in Flask** — replace synchronous notification calls with XADD to the appropriate stream; return immediately to the HTTP client.
4. **Add dead-letter handling** — messages that exceed max retries are moved to a `notifications:dead-letter` stream for manual inspection.
5. **Add Redis memory monitoring** — alert on stream memory usage; configure MAXLEN per stream based on throughput measurements.
6. **Revisit if throughput exceeds single-instance capacity** — if sustained traffic exceeds ~50,000 msgs/s (100× current, far beyond the 10× target), evaluate Redis Cluster or migration to Kafka. This ADR should be superseded at that point.

## Alternatives Considered

- **Apache Kafka** — Kafka's throughput, durable log, native consumer groups, and transactional exactly-once semantics are superior for high-volume, long-retention event streaming. We rejected it because: (1) no team experience and no dedicated infra engineer makes operating a Kafka cluster a significant risk; (2) the 2-week time-to-value constraint cannot be met with Kafka provisioning, configuration, and training; (3) managed Confluent Cloud exceeds our budget; (4) our throughput requirements (~500 req/s, 10× target of ~5,000 req/s) are 2–3 orders of magnitude below Kafka's design center. We would revisit Kafka if traffic exceeded ~50,000 msgs/s, if we needed multi-service event sourcing, or if the team grew to include dedicated infrastructure engineers.

- **PostgreSQL LISTEN/NOTIFY with a queue table** — Simpler than Kafka, already in our stack, and provides durability. Rejected because: (1) LISTEN/NOTIFY is not durable — messages are lost if no listener is connected; (2) polling a queue table under high write load competes with our primary database workload and increases lock contention; (3) no built-in consumer groups or retry mechanisms — we would build these from scratch. Redis Streams provide consumer groups, pending-entry tracking, and automatic claim transfer out of the box.

- **RabbitMQ** — Mature, supports dead-letter exchanges, retry logic, and message acknowledgment. Rejected because: (1) introduces a new distributed system (like Kafka) with corresponding operational overhead; (2) RabbitMQ's sweet spot is routing-heavy workloads with complex topologies — our notification fan-out is simple (produce to stream, consume by group); (3) would require the team to learn and operate another piece of infrastructure within the 2-week constraint. Redis Streams serve our simpler topology without adding a new operational dependency.