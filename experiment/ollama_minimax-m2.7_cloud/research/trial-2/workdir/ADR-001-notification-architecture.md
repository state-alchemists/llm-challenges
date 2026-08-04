# ADR-001: Notification Subsystem Message Broker Selection

## Status

**Proposed**

---

## Context

### Problem Statement

The notification module (email + webhook) runs synchronously inside the Flask HTTP request cycle. This causes:

- **Request timeouts**: Average notification latency is 800ms, spiking to 8s at peak. This directly degrades API response times for all users.
- **Silent failures**: A failed email provider call or slow webhook endpoint results in a dropped notification with no retry, no logging, and no visibility.
- **Cascading failures**: Two incidents where a single slow webhook endpoint exhausted connection pools, causing unrelated features to fail.
- **No delivery guarantee**: Billing-critical notifications ("trial expired", "payment failed") have no exactly-once guarantee, creating real revenue risk.

### Scaling Target

The system must:
1. Process notifications asynchronously (decoupled from HTTP responses)
2. Retry with exponential backoff on failure
3. Guarantee **at-least-once** delivery for all events; **exactly-once** for billing-critical events
4. Support WebSocket push notifications within 2 quarters without re-architecting
5. Handle 10x traffic growth (500 req/s → ~5,000 req/s at peak) without structural changes

### Constraints

| Constraint | Implication |
|---|---|
| Team: 6 engineers (3 senior, 3 mid-level), no dedicated infra/DevOps | Operational burden must be low; cannot run complex distributed systems |
| No Kafka experience on team | Kafka has significant learning curve and operational complexity |
| Already running Redis (session storage + rate limiting) | Redis expertise exists; incremental operational cost is low |
| Must deliver value within 2 weeks | Cannot absorb long migration or steep learning curves |
| Modest budget | Cannot afford Confluent Cloud or managed Kafka at scale |
| Exactly-once required for billing events | Requires idempotent consumers + deduplication mechanism |

### Observed Load

- ~2M tasks/month → ~22 events/sec average
- Peak: 500 req/s with notification bursts → ~150 notifications/sec at peak (1–3 notifications per task event)
- Target: 10x growth → ~1,500 notifications/sec sustained

This is a **low-to-medium throughput** workload. Throughput is not the primary driver; operational simplicity, ordering guarantees, and delivery semantics are.

---

## Decision

**Chosen: Redis Streams**

Redis Streams is selected as the message broker for the notification subsystem. Notifications will be produced to a `notifications` stream from the Flask application and consumed by a pool of async worker processes using `RedisStreamConsumer` with the `XREADGROUP` / `XACK` primitives.

A deduplication table (Redis hash keyed by `notification_id`) combined with idempotent consumer logic will provide exactly-once delivery for billing events. Exponential backoff will be implemented via `XREAD` block timeout + retry counter in the message payload, with a dead-letter stream (`notifications.dlq`) after max retries.

---

## Consequences

### Pros

**Operational simplicity**
- Redis is already running in production for session storage and rate limiting. No new infrastructure, no new deployment pipelines, no new monitoring systems to learn.
- Team already has Redis operational expertise. Marginal operational cost is near zero.

**Delivery guarantees**
- `XREADGROUP` + `XACK` provides at-least-once delivery with automatic re-delivery of unacknowledged messages on consumer failure.
- A `notification_id` deduplication key (stored in a Redis hash with a 24h TTL) combined with idempotent consumer logic delivers exactly-once semantics for billing events — matching the hard requirement.

**Ordering**
- Redis Streams maintains insertion order within a consumer group. For notifications tied to task state transitions (e.g., "task assigned" → "task completed"), ordering is preserved per `task_id` using the stream key as a partition shim.

**Retry and DLQ**
- A retry counter field in the message payload (incremented on each `XACK` without success) gates re-reading from the stream. After N retries, messages are moved to `notifications.dlq` via `XADD`. Workers read from DLQ with a slower polling interval for manual inspection or replay.

**Scales to 10x target comfortably**
- Redis Streams on a single instance handles ~50,000–100,000 messages/sec. The target of ~1,500/sec is well within reach. For WebSocket push notifications at 2 quarters, Redis Pub/Sub can be layered on the same Redis instance for real-time fan-out.

**Two-week delivery is achievable**
- Redis Streams has a straightforward API: `XADD`, `XREADGROUP`, `XACK`, `XRANGE`. A working prototype can be running in days. Migration of the existing synchronous notification calls to fire-and-forget `XADD` producers takes hours.

**Exactly-once for billing**
- By storing a deduplication key (`billing:{event_id}`) in a Redis hash with a 7-day TTL before processing, and checking it at consumption time, the system achieves exactly-once for billing events without distributed transactions.

### Cons

**No native topic routing**
- Redis Streams is a single stream (or sharded across streams by key manually). Kafka's rich topic-based routing (multiple consumer groups, per-topic lag monitoring) is not available. Workaround: use a discriminator field in the message payload and route via consumer group subscriptions, or maintain separate streams per notification type (`notifications.email`, `notifications.webhook`, `notifications.billing`). This adds minor complexity.

**Persistence depends on Redis RDB/AOF**
- If Redis is restarted, streams are replayed from RDB snapshot or AOF log. At the current scale (~150 msg/sec), replay is fast. However, Redis as the sole message store means its durability configuration (AOF `everysec` or `always`) directly affects delivery guarantees. Must configure AOF with `appendfsync everysec` minimum; `always` for stronger guarantees at minor throughput cost.

**Consumer group rebalancing under load**
- If a consumer dies, `XREADGROUP` rebalances unacknowledged messages to other consumers. With 6 engineers and likely 2–4 notification workers, this is manageable. At much larger scale (dozens of workers), Kafka's partition-based rebalancing is more battle-tested.

**No native dead-letter queue mechanism**
- Redis Streams does not have a built-in DLQ. The workaround (manual `XADD` to a `.dlq` stream after max retries) is simple but requires discipline. Kafka's native DLQ topic support is more robust.

**Long poller complexity**
- `XREAD BLOCK` timeout must be tuned. Too short → busy-waiting; too long → latency on low-volume streams. At 150 msg/sec this is not a practical concern, but as volume grows this parameter needs attention.

---

## Alternatives Considered

### Apache Kafka

**Why it was considered**

Kafka is the industry standard for event streaming at scale. It offers superior throughput (millions of events/sec), rich topic-based routing, proven exactly-once semantics via Kafka Transactions, mature consumer group rebalancing, and excellent operational tooling (Kafka Connect, Schema Registry, MirrorMaker 2).

**Why it was rejected**

| Factor | Kafka | Decision impact |
|---|---|---|
| Operational complexity | Requires ZooKeeper or KRaft, topic partitioning, partition leadership, replication factor configuration, and broker monitoring. With no dedicated infra engineer, this is a significant burden. | **Major negative** |
| Learning curve | Team has zero Kafka experience. Producing and consuming messages correctly (offset management, consumer group state, rebalancing, idempotent producers) requires meaningful ramp-up time. | **Major negative — violates 2-week constraint** |
| Infrastructure cost | Running Kafka on EC2 requires at minimum 3 brokers for HA, plus ZooKeeper nodes. Even with 3 `t3.medium` instances the cost is ~$150–200/month, vs. zero incremental cost using existing Redis. | **Moderate negative** |
| Throughput fit | Target load is ~1,500 notifications/sec. Kafka handles this trivially but with significant architectural overhead. Kafka is designed for hundreds of MB/s of throughput; this workload is orders of magnitude below its design point. | **Over-engineered** |
| Exactly-once for billing | Kafka Transactions provide exactly-once semantics, which is superior to the Redis deduplication approach. However, Kafka exactly-once requires careful configuration and adds consumer complexity. | **Minor advantage, not decisive** |
| WebSocket support | Kafka has no native Pub/Sub for WebSocket push. Would still need Redis Pub/Sub or a separate WebSocket server infrastructure. | **No advantage** |

**Conclusion on Kafka**: Kafka is the correct choice for a high-throughput, multi-team, multi-consumer ecosystem where topic routing, schema evolution, and ecosystem integration (Kafka Connect for S3, Elasticsearch, etc.) are requirements. For a 6-person team with an existing Redis footprint, modest scale, and a 2-week deadline, Kafka's operational overhead is disproportionate to the problem.

### Redis Streams vs. Kafka — Summary Comparison

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| Throughput (msg/sec) | 50,000–100,000 (single node) | Millions (clustered) |
| Message retention | Until explicitly trimmed (`XTRIM`) or by `MAXLEN` | Configurable time/size based (compacted or retention-based) |
| Ordering | Per stream, per consumer group | Per partition |
| Consumer groups | Yes (`XREADGROUP`) | Yes (richer rebalancing) |
| At-least-once delivery | Yes (`XACK`-based) | Yes (offset-based) |
| Exactly-once delivery | Via idempotent consumers + deduplication | Native via Kafka Transactions |
| Dead-letter queue | Manual (`XADD` to DLQ stream) | Native DLQ topic support |
| Infrastructure required | Existing Redis instance | 3+ brokers + ZooKeeper/KRaft |
| Operational learning curve | Low (team has Redis experience) | High (no experience) |
| Setup time | Days | Weeks |
| Cost (infra) | $0 incremental | $150–200/month minimum |
| WebSocket real-time | Native via Redis Pub/Sub | Requires separate layer |

---

## Recommendation

**Redis Streams is the correct choice given the constraints.**

The team already operates Redis. The notification workload (~1,500/sec sustained) is well within Redis Streams' comfortable operating range. The learning curve is minimal, the setup time meets the 2-week constraint, and exactly-once for billing events is achievable via idempotent consumers with a deduplication key. Kafka would deliver more theoretical robustness in an idealized world, but for a 6-person team with no Kafka experience and a tight timeline, Kafka's operational complexity would delay delivery and add infrastructure cost without meaningful benefit at this scale.

**Implementation priorities for the first two weeks:**

1. Replace synchronous notification calls in Flask with `XADD` fire-and-forget producers (hours)
2. Stand up 2–4 async worker processes using `XREADGROUP` / `XACK` (days)
3. Implement retry counter + DLQ routing (days)
4. Implement billing event deduplication via Redis hash (days)
5. Add monitoring: stream length (`XLEN`), consumer lag (`XPENDING`), DLQ depth (days)

At 2 quarters, when WebSocket push notifications are needed, Redis Pub/Sub can share the same Redis instance for real-time fan-out to WebSocket servers — no new infrastructure required.
