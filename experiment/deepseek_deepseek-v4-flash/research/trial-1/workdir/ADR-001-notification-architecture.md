# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

---

## Context

The notifications module in our SaaS project management platform sends emails and webhooks when tasks are updated, assigned, or completed. It currently runs synchronously inside the Flask HTTP request cycle, causing:

- **Request timeouts** — average 800 ms latency, spikes to 8 s during peak hours (~500 req/s).
- **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry or dead-letter queue.
- **Cascading failures** — two incidents this year where a slow webhook consumed a connection from the pool, taking down unrelated features.
- **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") require at-least-once delivery with exactly-once processing semantics, which the current synchronous model cannot provide.

**Scaling targets:**
- Decouple notifications from the HTTP request cycle.
- Support retry with exponential backoff.
- Guarantee at-least-once delivery (exactly-once processing for billing events).
- Add real-time WebSocket push notifications within two quarters.
- Handle 10x traffic growth without re-architecting.

**Team constraints:**
- Six engineers (three senior, three mid-level), no dedicated infrastructure engineer.
- Redis is already in production (session storage, rate limiting).
- No Kafka experience on the team.
- Must deliver value in <=2 weeks.
- Budget too modest for managed Confluent Cloud at full scale.

---

## Decision

**Adopt Redis Streams** for the notification subsystem's message broker.

The HTTP request cycle will enqueue notification events into a Redis stream. A pool of background workers (Python processes using `redis-py` with consumer groups) will read, process, and acknowledge messages. Failed deliveries return to the stream via `XPENDING` / `XCLAIM` for retry with exponential backoff. Billing notifications carry an idempotency key so that at-least-once delivery yields exactly-once processing. WebSocket push in Q2 will be served by a lightweight bridge reading the same stream or subscribing to a Redis Pub/Sub channel derived from stream events.

---

## Consequences

### Pros

1. **No new infrastructure.** Redis is already deployed and managed. No additional brokers, ZooKeeper/KRaft clusters, or JVM tuning. The ops burden is close to zero — `redis-py` handles the client protocol, and the team already monitors Redis.

2. **Fastest path to value.** A consumer-group reader, a retry loop, and an idempotency table in PostgreSQL can ship within one week. The 2-week constraint is comfortable, not tight.

3. **Adequate throughput.** Redis Streams sustain 100k+ messages/second on modest hardware. Our current peak is ~500 req/s; 10x growth is ~5,000 req/s. Redis has orders of magnitude of headroom before it becomes a bottleneck.

4. **Natural fit for WebSocket push.** Redis Pub/Sub — already a first-class Redis feature — maps directly to real-time push. A small bridge process can subscribe to a notification channel and fan out to WebSocket connections, avoiding Kafka's additional bridge infrastructure.

5. **Team familiarity.** The team already uses Redis for session storage and rate limiting. The stream and consumer-group API (`XADD`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`) is straightforward and well-documented. No learning curve for JVM tuning, partition sizing, or Kafka's consumer rebalancing protocol.

6. **At-least-once delivery via consumer groups.** Redis consumer groups track delivery with a pending entries list (PEL). Unacknowledged messages are rediscovered via `XPENDING` and claimed by another consumer. Combined with idempotent processing (idempotency key + unique constraint in PostgreSQL), this satisfies the exactly-once processing requirement for billing events.

7. **Retry with exponential backoff is straightforward.** A retry stream (or a dead-letter set via `XADD` to a separate stream with a TTL) is simple to implement. The `max_delivery_count` pattern is a few dozen lines of Python.

### Cons

1. **Memory-bound storage.** Unlike Kafka, which writes to disk by default and can retain terabytes of messages for weeks, Redis Streams live primarily in memory (AOF append-log provides crash recovery but does not function as a message dump). Long-term retention of historical events for replay or audit requires explicit offloading to S3 or PostgreSQL. For notification delivery (minutes-to-hours retention) this is not a problem; for audit-trail use cases it must be designed upfront.

2. **No built-in partitioning.** Kafka distributes a topic across partitions on multiple brokers automatically. Redis streams live on a single node (or a single shard in a cluster). To scale beyond a single node's memory or throughput, you must manually shard by a key (e.g., `stream:notifications:{tenant_id}`). At our projected 5,000 req/s peak this is unlikely to be necessary, but it is a design gap if growth surprises us.

3. **Crash-recovery window.** With AOF `appendfsync everysec`, up to 1 second of messages can be lost on an unclean shutdown. This is acceptable for notification delivery (at-least-once) but means billing criticality depends on the idempotency key, not on the broker's durability guarantee. Configuring `appendfsync always` removes the window at a ~30% write throughput cost — a trade-off worth evaluating for the billing stream specifically.

4. **Consumer rebalancing is manual compared to Kafka.** Kafka's group coordinator automatically reassigns partitions when a consumer joins or leaves. Redis consumer groups require the application to handle `XCLAIM` for unprocessed messages after a consumer failure. The team must implement a heartbeat/claim mechanism. This is well-understood and not complex, but it is code they would not write with Kafka.

5. **No Kafka ecosystem integration.** Kafka Connect (dozens of pre-built source/sink connectors) and ksqlDB do not apply here. If the team later wants to stream notifications to a data lake or integrate with a third-party event bus, they would need to build the bridge themselves. Given the team size and the current absence of such requirements, this is acceptable deferred complexity.

---

## Alternatives Considered

### Apache Kafka

**Rejected** — not due to technical inadequacy, but due to a mismatch with team capability, operational capacity, and delivery timeline.

Kafka excels at exactly what Redis Streams does adequately:
- Persistent, disk-backed message log with configurable retention.
- Automatic partition-based scaling across a cluster.
- Strong ordering guarantees within a partition.
- Consumer group rebalancing with automatic partition assignment.
- Exactly-once semantics (EOS) within the Kafka pipeline via transactional producers.

However, the team constraints tip the balance decisively against it:

1. **Operational cost.** Self-hosting Kafka requires managing ZooKeeper (or KRaft brokers), tuning JVM heap and GC, sizing disk I/O for page cache performance, and handling partition rebalancing. A 6-person team with no infrastructure engineer — and no Kafka experience — would spend more time learning and operating Kafka than building the notification system. Managed Kafka (Confluent Cloud, MSK) is budget-prohibitive at our scale.

2. **Delivery timeline.** Installing, configuring, and learning Kafka — then building the producer/consumer layer and deployment pipeline — would consume most of the 2-week constraint before any business logic is written. Redis Streams can produce a working system in under a week.

3. **Over-provisioned.** Kafka is designed for 1M+ messages/second, multi-datacenter replication, and year-long retention. Our peak is 500 req/s. The complexity tax is paid upfront for capacity we will not use for years — if ever. Redis Streams maps directly to the actual workload.

4. **WebSocket push gap.** Kafka has no native Pub/Sub for real-time push to browsers. We would need an additional bridge (Kafka -> WebSocket proxy) that Redis Streams avoids entirely.

Kafka would be appropriate if: the team were larger with dedicated ops, the throughput requirement exceeded 100k msgs/s, or we needed years-long event retention for a full event-sourcing architecture. None of those apply today.
