# ADR-001: Notification Subsystem Message Broker

**Status:** Proposed

## Context

Our SaaS project management platform (85,000 MAU, ~2M tasks/month, 500 req/s peak) handles all notification delivery — emails and webhooks for task events, plus billing-critical alerts — synchronously inside the HTTP request cycle. This has caused four production problems:

1. **Request timeouts** — notification dispatch blocks responses (avg 800ms, spikes to 8s).
2. **Silent failures** — no retry or dead-letter queue when downstream providers are down.
3. **Cascading failures** — slow webhook endpoints have exhausted the DB connection pool twice this year, taking down unrelated features.
4. **No delivery guarantees** — billing notifications ("trial expired", "payment failed") have no at-least-once or exactly-once assurance.

We must decouple notification processing from request handling, add retry with exponential backoff, guarantee at-least-once delivery for billing events (exactly-once where feasible), support real-time WebSocket push within two quarters, and absorb 10x traffic growth without re-architecting.

Key constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Stack**: Python/Flask monolith, PostgreSQL, Redis already in production for sessions and rate limiting.
- **Experience**: No Apache Kafka expertise on the team.
- **Timeline**: Must deliver value within 2 weeks of starting migration.
- **Budget**: Modest — managed Confluent Cloud at full scale is not affordable.
- **Correctness**: Billing notifications require exactly-once delivery semantics.

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams meets our throughput requirements, integrates with our existing Redis deployment, and can be operational in days rather than weeks. Exactly-once semantics for billing notifications will be achieved through application-level idempotency (PostgreSQL-backed deduplication), not broker-level transactional guarantees — a pattern that is well-established and sufficient for our volume.

Kafka is the stronger technical choice at extreme scale, but our current and projected load (5,000 req/s at 10x growth) is well within Redis Streams' capacity, and our operational constraints make Kafka's overhead unjustifiable today.

## Consequences

### Pros

- **Fast time to value.** Redis is already in production. The team configures a new Streams-based consumer group, writes a producer module, and ships — no new infrastructure to provision, monitor, or learn. Estimated: 3–5 days to a working async pipeline.
- **Low operational burden.** Redis Streams reuse the existing Redis instance (or a dedicated Redis node at modest cost). No ZooKeeper/KRaft cluster, no partition rebalancing to debug, no separate monitoring stack. A 6-person team without a dedicated infra engineer can maintain it.
- **Per-stream ordering.** Redis Streams guarantee strict ordering within a single stream (stronger than Kafka's per-partition guarantee). This simplifies reasoning about notification sequence for a given tenant or task.
- **Consumer groups with pending entries.** `XREADGROUP` and `XPENDING` provide built-in consumer-group semantics with explicit acknowledgement (`XACK`). Unacknowledged messages are automatically visible for retry — the foundation for at-least-once delivery and exponential backoff.
- **Sufficient throughput.** Redis Streams handle tens of thousands of messages per second on a single node. Our 10x peak projection (~5,000 req/s) leaves significant headroom.
- **Cost-efficient.** No additional managed-service fees. A dedicated Redis node on AWS ElastiCache (if needed) costs a fraction of Confluent Cloud.
- **Future WebSocket support.** Redis Pub/Sub already pairs with Streams for fan-out. The real-time push notification requirement (within 2 quarters) can layer Redis Pub/Sub alongside Streams without new infrastructure.

### Cons

- **No native exactly-once semantics.** Redis Streams provide at-least-once delivery. Achieving exactly-once for billing notifications requires application-level idempotency — we will implement this via a PostgreSQL deduplication table (idempotency key = `notification_type + entity_id + event_id`). This is a standard, proven pattern but adds application complexity.
- **Limited message retention.** Redis Streams use `MAXLEN` or time-based trimming. Unlike Kafka's configurable log retention and compaction, old messages are pruned by the stream's max-length policy. For audit purposes, we will persist notification state in PostgreSQL before acknowledging the stream message, making the stream a transient transport rather than a durable log.
- **No built-in schema registry.** Kafka's Confluent ecosystem includes schema evolution (Avro, Protobuf). We will enforce message contracts via Python dataclasses with JSON serialization and version fields — adequate for a small team, but manual.
- **Single-node bottleneck risk.** Redis Streams on a single node have no Kafka-style partition parallelism within one stream. Mitigation: shard by topic (billing notifications, task notifications, webhook notifications) into separate streams, each independently consumable. At 10x scale, a Redis Cluster deployment distributes streams across nodes.
- **Operational fragility if misconfigured.** `MAXLEN` set too low drops messages before consumption; set too high consumes memory. We will set conservative limits (e.g., `MAXLEN ~ 100000`) and monitor stream length and consumer lag via Redis `XINFO` metrics exported to CloudWatch.
- **Not a replacement for a true event log.** If the platform eventually needs a durable, replayable event log for CQRS or event sourcing, Redis Streams alone will not suffice. At that point, we would revisit Kafka or a similar solution — but that is a different problem from async notification delivery.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event streaming platform with first-class exactly-once semantics (idempotent producers + transactional consumer groups), configurable retention and log compaction, built-in consumer-group rebalancing with partition-based parallelism, and a rich ecosystem (schema registry, Kafka Connect, ksqlDB).

We rejected Kafka for this decision because:

- **Operational overhead exceeds team capacity.** Kafka requires cluster management (ZooKeeper or KRaft), partition planning, broker monitoring, and rebalancing expertise. A 6-person team without a dedicated infra engineer and with zero Kafka experience would need weeks of learning before shipping value — violating the 2-week constraint.
- **Managed Kafka is expensive.** Confluent Cloud at our projected scale (5,000 msg/s peak) would cost significantly more than an additional ElastiCache Redis node, conflicting with the modest budget constraint.
- **Throughput is overkill.** Kafka's design targets are in the millions of messages per second. Our 10x peak projection is ~5,000 req/s — two orders of magnitude below Kafka's floor. The complexity tax is not justified by our volume.
- **Exactly-once can be achieved differently.** Kafka's transactional exactly-once semantics are powerful, but for our use case — billing notifications at modest volume — application-level idempotency via PostgreSQL is simpler, equally correct, and does not require re-architecting the delivery pipeline.

Kafka remains the right choice if the platform later adopts CQRS/event sourcing or needs multi-consumer log replay across many services. That is a future decision, not this one.

### Other alternatives briefly considered

- **RabbitMQ**: Strong per-message routing and dead-letter queues, but introduces a separate broker to operate. No advantage over Redis Streams given we already run Redis, and the operational learning curve is steeper.
- **SQS + SNS (AWS native)**: Fully managed, no infra overhead. However, it couples us to AWS, lacks the consumer-group model we need for parallel workers, and the per-request pricing at 10x scale is less predictable than a fixed Redis instance. SQS also provides only at-least-once, requiring the same application-level idempotency we'd need with Redis Streams — without the benefit of reuse.
- **Database-backed queues (Postgres SKIP LOCKED)**: Zero new infrastructure, but polling puts load on the already-stressed PostgreSQL primary, and this pattern does not support the fan-out needed for WebSocket push. Mixing transactional workload with queue workload in the same database is a known anti-pattern at our scale.