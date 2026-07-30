# ADR-001: Notification Subsystem — Async Message Broker

**Status:** Proposed

---

## Context

The notifications module sends emails and webhooks when tasks are updated, assigned, or completed. In the current architecture, these are sent synchronously inside the HTTP request cycle. As the platform has grown to ~85,000 MAU and ~500 req/s peak, this coupling has caused:

- Request timeout spikes up to 8s during peak hours
- Silent notification drops when email providers or webhook endpoints fail
- Two cascading-failure incidents where a slow webhook endpoint exhausted the connection pool and took down unrelated features
- No delivery guarantees for billing-critical notifications (trial expiry, payment failures)

We need to decouple notification dispatch from the HTTP request cycle and introduce an async message broker. The broker must support at-least-once delivery, retry with exponential backoff, a path to exactly-once for billing events, and be forward-compatible with planned WebSocket push notifications within two quarters.

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid), no dedicated infrastructure engineer
- **Existing infrastructure**: Redis already deployed for session storage and rate limiting. No Kafka in the stack.
- **Team skills**: No Kafka experience on the team today.
- **Time-to-value**: Must deliver within 2 weeks of setup/migration work.
- **Budget**: Modest — managed Confluent Cloud is out of reach at full scale.
- **Scaling target**: 10x traffic growth without re-architecting.
- **Correctness**: Exactly-once semantics required for billing notifications.

---

## Decision

**Use Redis Streams.**

Redis Streams will serve as the message broker for the notification subsystem. Notification-producing code in the Flask monolith will `XADD` messages to named streams. A separate background worker process (Python, consuming via `XREADGROUP`) will pull messages, dispatch emails/webhooks, and acknowledge them. Retry logic with exponential backoff operates on a separate retry stream or pending-entry list.

Redis Streams is chosen over Kafka for this context because the decisive factors are **team velocity and operational simplicity**, not raw throughput or maximum retention.

---

## Consequences

### ✅ Pros

1. **Zero new infrastructure.** Redis is already deployed, monitored, backed up, and familiar to operations. No new ZooKeeper/KRaft brokers, no new JVM tuning, no new networking or storage provisioning. The team can start experimenting within hours, not weeks.

2. **Immediate team velocity.** Every engineer on the team already knows how to talk to Redis (`rpush`/`blpop` patterns for queues; streams are a natural extension). The learning curve is shallow — the core API is five commands (`XADD`, `XREAD`, `XREADGROUP`, `XACK`, `XPENDING`). The notification worker can be written in Python with `redis-py`; no new client library ecosystem to learn.

3. **Consumer groups with minimal complexity.** Redis Streams' consumer group model (`XREADGROUP`) provides automatic consumer-side failover and message re-delivery, matching the pattern Kafka pioneered but with Redis's "keep it simple" surface area. Each notification worker instance joins the group; when one fails, its pending messages are re-assigned to another consumer after a configurable idle timeout.

4. **Retry and DLQ are straightforward.** Pending entries (`XPENDING`) serve as the retry mechanism. Messages that exceed the retry limit can be `XADD`ed to a dead-letter stream. The same worker pattern, the same tools, no special infrastructure.

5. **Adequate at current and near-term scale.** Redis Streams handles 100k+ messages/s on modest hardware. Our peak is ~500 req/s, each producing perhaps 1–3 notifications. A single Redis instance (our existing deployment) is not the bottleneck. At 10x growth (~5,000 req/s), Redis Streams still holds comfortably with a modestly provisioned instance, and sharding across multiple Redis nodes is a well-documented escape hatch.

6. **Natural path to exactly-once.** Redis Streams does not provide exactly-once messaging natively, but the practical pattern is the same one used with Kafka in most real-world deployments: **at-least-once delivery + idempotent consumers**. Our billing service can deduplicate webhook deliveries by notification ID stored in a `notifications_delivered` table (PostgreSQL unique constraint). At ~1M tasks/month, the dedup key space is small. For the rare case where Redis crashes between `XADD` and persistence flush, manual reconciliation from the PostgreSQL task log is possible because all notification-producing code reads from the database first. This is a known, well-understood compromise — far better than the current silent-drop behavior.

7. **Paves the way for WebSocket push.** The same worker that consumes from Redis Streams can also publish to a Redis Pub/Sub channel or an in-memory broadcast for WebSocket servers. Redis is already central to this flow; adding WebSocket push in two quarters plugs into the same infrastructure.

### ❌ Cons

1. **No built-in long-term retention.** Redis Streams are bounded by available memory and the `MAXLEN` trimming policy. Messages are not stored on disk for weeks of replay (unlike Kafka's log, which writes to disk and retains by configurable policy). If we later need heavy event replay for analytics or debugging across a multi-day window, Redis Streams will be significantly more awkward: we would need to archive messages to S3 or PostgreSQL as a side effect of consumption.

2. **Consumer rebalancing is primitive.** When a Kafka consumer joins or leaves a group, the group coordinator rebalances partition assignment cleanly (partition-level granularity, with configurable `session.timeout.ms`). Redis Streams rebalances at the **consumer level**, not the partition level — Redis distributes messages from a single stream across all consumers in a group round-robin. This means a consumer crash may cause brief duplicate processing as the idle-timeout window expires and other consumers re-read pending messages. The dedup strategy (point 6 in Pros) absorbs this, but Kafka's model is cleaner at scale.

3. **Scalability ceiling is lower.** A single Redis Stream resides on one Redis node. To scale beyond what one node can handle, you must manually shard streams across nodes (e.g., tenant-based stream names). Kafka's partitioning is built into the protocol and handled by the broker. For 10x growth (5,000 req/s), Redis is fine. For 100x (50,000 req/s), sharding Redis Streams becomes a significant operational task. This is a long-term risk, not an immediate one.

4. **Persistence guarantees are weaker.** Redis persistence (RDB snapshots at intervals, or AOF with `fsync=everysec`) is not as durable as Kafka's disk log. An unclean Redis shutdown can lose up to 1 second of messages (AOF `everysec`) or more (RDB). For billing notifications, this means the dedup/retry layer must handle the gap — which it already does, but Kafka would have eliminated the gap entirely. Acceptable for the trade-off.

5. **No built-in partition ordering across keys.** Kafka guarantees order within a partition. Redis Streams guarantees order within a single stream. If we need strict cross-stream ordering (e.g., "task update before task completion"), the application must manage that — typically by routing related events to the same stream, or by timestamp correlation in the consumer. This is the same pattern as a single-partition Kafka topic, so it's not new complexity.

---

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for asynchronous event streaming and excels at the properties Redis Streams lacks: durable disk-backed retention, true exactly-once semantics (idempotent producers + transactions), clean consumer rebalancing, and horizontal scalability through partitioning.

**Why it was rejected:**

The decision is not about which technology is *better* — Kafka is objectively more capable at planetary scale. The decision is about which technology is *right for this team, at this stage, with these constraints.*

- **Operational cost is too high for a 6-person team with no infra engineer.** Kafka requires dedicated broker nodes, ZooKeeper or KRaft quorum management, JVM heap tuning, partition monitoring, and offset management. A single misconfigured `min.insync.replicas` or a partition leadership election that stalls can take down the messaging layer silently. The team would need weeks of ramp-up to confidently operate Kafka in production, plus a new monitoring dashboard, new alerting rules, and a runbook for at least half a dozen new failure modes. This is a disproportionate burden for a system that currently runs 500 req/s.

- **2-week delivery window is incompatible with Kafka's setup cost.** Standing up a production Kafka cluster (security, replication, monitoring, schema registry if Avro) takes 2–4 weeks for a team that doesn't already know the platform. Managed Kafka (Confluent Cloud, MSK) reduces operational burden but violates the budget constraint and still requires learning the client API, topic configuration, and consumer group semantics — all new to the team.

- **Overcapacity for the problem.** Kafka is designed for millions of events per second with multi-week retention, streaming joins, and exactly-once processing across multiple services. Our notification workload is 500–1,500 messages per second, with no cross-service streaming, no event sourcing, and no long-term retention requirement. Redis Streams is *the correct tool* for this payload. Deploying Kafka for this would be like putting a jet engine on a bicycle.

- **However, if the platform's trajectory changes** — if we adopt event sourcing, need weeks of message replay for audit, or grow to 50,000 req/s — **Kafka becomes the right answer.** Redis Streams is the pragmatic choice for now, and the consumer-group abstraction means the application code (stream name + group name + XREADGROUP loop) maps almost one-to-one to Kafka's consumer model. A future migration to Kafka would not require a rewrite of the notification worker; it would be a library swap.

---

## Summary

Redis Streams delivers immediate value (days, not weeks) with zero new infrastructure, minimal learning curve, and adequate headroom for 10x growth. The trade-offs — weaker durability, manual sharding at extreme scale, primitive rebalancing — are manageable through idempotent consumer design and are acceptable given the current team size and traffic profile.

**Definitive recommendation: Redis Streams.**
