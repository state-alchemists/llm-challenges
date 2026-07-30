# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

## Context

The Notifier subsystem sends emails and webhooks on task lifecycle events (creation, update, assignment, completion). It currently runs synchronously inside the Flask HTTP request cycle, causing three interrelated failures:

1. **Latency spikes**: Average handler latency is 800 ms, spiking to 8 s at peak, because the response waits on external I/O (SMTP, HTTP webhooks).
2. **Silent drops**: A dead SMTP relay or a 503 from a webhook endpoint means the notification is lost. No retry, no dead-letter queue.
3. **Cascading failures**: Slow webhooks exhaust the connection pool. Two incidents in the past year took down unrelated features (auth, task CRUD) as a result.

We need an async notification pipeline that decouples event production from delivery, provides retry with exponential backoff, guarantees at-least-once delivery with exactly-once semantics for billing-critical events, and supports real-time WebSocket push within two quarters.

The engineering team is 6 people (3 senior, 3 mid-level). No Kafka experience exists on the team today. We already run Redis for session storage and rate limiting. The budget does not cover managed Confluent Cloud at full scale. The solution must deliver value within two weeks of starting work.

## Decision

**Use Redis Streams**, backed by idempotent consumers for exactly-once billing semantics.

Redis Streams satisfy every stated requirement while keeping operational complexity within the team's capacity. Kafka is a better fit at a different scale and with a larger team, but introducing it here would burn the 2-week timeline on learning and operations, not on solving the actual problem.

## Consequences

### Advantages

- **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. No new cluster, no Zookeeper/KRaft, no JVM. Time to first message: hours, not weeks.
- **Team velocity.** The team already knows Redis client libraries (`redis-py`). The consumer group API (`XREADGROUP`, `XACK`, `XAUTOCLAIM`) is well-documented and Pythonic. No learning curve on partition management, retention policies, or rebalancing protocols.
- **At-least-once delivery out of the box.** Consumer groups track each consumer's pending entries in a PEL (Pending Entry List). If a consumer crashes before acknowledging, the message remains pending and is auto-redelivered (or reclaimed via `XAUTOCLAIM`) — no custom reliability layer needed.
- **Stream-based exactly-once via idempotency.** Redis Streams do not provide native exactly-once semantics. However, true exactly-once between a broker and an *external* system (email API, webhook endpoint) is impossible for any technology — the external system cannot participate in a distributed transaction. The correct pattern is **at-least-once delivery + idempotent consumers**. Each notification carries a unique ID (`notification.id = uuid4`); consumers deduplicate via a Redis SET with TTL or a database unique constraint before acting. This achieves exactly-once delivery regardless of broker choice.
- **Retry with backoff.** A `retry_count` and `next_retry_at` field in the stream message, combined with a scheduled consumer that re-enqueues expired retries, implements exponential backoff trivially.
- **WebSocket push path.** Future real-time WebSocket notifications can consume the same stream — no second pipeline to build. A dedicated consumer group reads events and pushes them over established WebSocket connections.
- **Throughput headroom.** At current peak (~500 req/s, only a fraction of which generate notifications), Redis Streams on existing hardware handle this with negligible overhead. After 10x growth (~5,000 req/s peak), a Redis cluster with 3 nodes (already modest) comfortably saturates the pipeline. Single-node Redis can sustain 100k+ stream writes/second on modern hardware.
- **Message retention.** Streams support capped retention via `MAXLEN` (~`XADD mystream MAXLEN ~10000 * field value`), keeping memory bounded while retaining enough history for replay or debugging. For billing events specifically, a separate stream with longer retention or a database-backed log provides audit-compliant persistence.

### Disadvantages

- **No native ordering beyond a single stream.** Redis Streams guarantees ordering within one stream (and within one shard of a sharded setup). To fan out across partitions, you need multiple streams or application-level partitioning — Kafka's partitioning model is more mature. That said, at this scale a single stream per event type is sufficient; partitioning is premature.
- **Memory-bound retention.** Stream data lives in RAM (with optional AOF/RDB persistence). A sustained 10x traffic spike over days could pressure memory. Mitigation: set aggressive `MAXLEN`, archive billing events to PostgreSQL, and monitor memory headroom. If memory becomes the bottleneck, scaling vertically or sharding across streams is simpler than migrating to Kafka.
- **No compaction.** Redis Streams lack log compaction (a Kafka feature that retains only the latest message per key). Not relevant for the notification use case — we never compact notifications.
- **Smaller ecosystem.** Kafka has a richer ecosystem of connectors (Kafka Connect), stream processors (Kafka Streams, Flink), and schema registries. Redis Streams have none of these. For a 6-person team with no Kafka experience, this is actually a *feature* — fewer moving parts means fewer failure modes.
- **Exactly-once requires discipline.** No native EOS means every consumer must implement idempotency. This is a one-time cost (a `dedup()` function wrapping Redis SET or a DB constraint) and is the correct pattern regardless of broker choice when sinks are external APIs.

## Alternatives Considered

### Apache Kafka (Rejected)

**Why it was attractive:** Kafka is the gold standard for event streaming. It provides native exactly-once semantics (transactional producer/consumer), log compaction, multi-decade durability, and unbounded horizontal scaling. If this were a 50-person engineering org processing 50k events/second across 30 microservices, Kafka would be the clear choice.

**Why it was rejected for this context:**

- **Operational tax is too high.** Kafka requires running and tuning a separate cluster (Zookeeper or KRaft, brokers, controller nodes). Topic tuning (partition count, replication factor, retention size/ time, segment sizing, ISR configuration) demands experience the team does not have. A misconfigured consumer that falls behind by millions of messages requires partition rebalancing expertise to recover. Redis Streams has none of these failure modes — the team already manages Redis.
- **Timeline is unworkable.** Two weeks from start to value delivery. In that window, a Kafka-first team would: provision infrastructure, tune the cluster, learn the Python Kafka client (`confluent-kafka-python` vs `aiokafka`), design the topic/partition model, build the consumers, test, and deploy. A Redis Streams team would: install `redis-py` (already installed), write the stream producer call (5 lines), write the consumer with `XREADGROUP` (30 lines), test, and deploy. The difference is roughly 10 days vs. 2 days for the initial async pipeline.
- **Exactly-once is not actually needed from the broker.** Kafka's EOS applies to read-process-write cycles *within Kakfa* (consume from topic A, process, produce to topic B). For external sinks (email, webhooks), the sink cannot participate in the two-phase commit — so exactly-once between Kafka and the external system is also impossible. Both Kafka and Redis Streams achieve exactly-once delivery to external systems via the same mechanism: idempotent consumers. Kafka's EOS advantage evaporates for this use case.
- **Managed Kafka is too expensive.** Confluent Cloud for modest throughput starts around ~$500-$1,000/month for a small cluster. Self-hosted Kafka on EC2 adds 2-3 instances plus monitoring overhead. Redis Streams adds $0 to the existing Redis bill.
- **Over-engineered for the load.** A tool that handles 1M+ messages/second per partition is being evaluated for a pipeline that averages < 1 event/second. The headroom buys nothing; the operational complexity costs everything.
- **WebSocket path is equally easy on both.** Both Kafka and Redis Streams can feed a WebSocket broadcast layer. Redis has the advantage of its `PUBLISH`/`SUBSCRIBE` as a complementary tool for real-time fan-out, but the Streams-based approach works too.

### Amazon SQS / SNS (Considered but out of scope for this ADR)

The constraints say we host on AWS but also mention a modest budget. SQS is a viable alternative and simpler than either Kafka or Redis Streams in some ways. It was excluded from this ADR per the stated options — we compare only Amazon SQS/SNS in a follow-up ADR if needed. Key trade-off: SQS eliminates all operational overhead but loses ordered delivery (unless using FIFO queues, which cap throughput at 300 TPS) and cannot naturally support the planned WebSocket push path without a separate SNS → WebSocket bridge.
