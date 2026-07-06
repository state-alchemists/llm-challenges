# ADR-001: Notification Subsystem — Async Messaging Backbone

**Status:** Proposed

---

## Context

The Notifier module sends email and webhook notifications when tasks are updated, assigned, or completed. Currently it runs synchronously inside the Flask HTTP request cycle. As the platform has grown to 85,000 MAU / ~2M tasks/month / ~500 req/s peak, this coupling has caused three classes of production harm:

1. **Request timeouts** — average notification latency of 800 ms, spiking to 8 s during peak hours, directly inflating p95 response times for all API requests.
2. **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry, no dead-letter queue, no alert.
3. **Cascading failures** — two incidents this year where a slow webhook exhausted the DB connection pool, taking down unrelated features.

We need an asynchronous messaging backbone to decouple notification dispatch from the request cycle. The required characteristics are:

| Requirement | Detail |
|---|---|
| Async decoupling | Producers (HTTP handlers) must not block on delivery. |
| Retry with backoff | Failed deliveries must be retried automatically; permanently failed messages must land in a dead-letter queue. |
| At-least-once delivery | Billing-critical events (trial expired, payment failed) must not be lost. |
| Exactly-once semantics for billing | Billing events must be delivered and processed exactly once, on the consumer side, as close to that guarantee as the infrastructure permits. |
| Future WebSocket push | Real-time push notifications (WebSocket) must be supported within two quarters. |
| 10× headroom | The choice must handle ~5,000 req/s peak (10× current load) without re-architecting. |
| Team fit | 6 engineers (3 senior, 3 mid-level). No dedicated infrastructure engineer. No Kafka experience on the team today. |
| Fast time-to-value | Must deliver measurable benefit within ≤2 weeks of starting work. |
| Budget | Modest — cannot bear managed Confluent Cloud at full scale today. |

We already run Redis in production for session storage and rate limiting.

---

## Decision

**Adopt Redis Streams** as the notification messaging backbone.

Producers will `XADD` notification events to Redis streams. Consumer workers, organised into consumer groups, will `XREADGROUP` to claim and process messages, `XACK` on success, and rely on the PEL (Pending Entry List) with `XAUTOCLAIM` for retry and dead-letter routing.

Billing-critical notifications will carry an idempotency key; consumers will deduplicate against a Redis-backed deduplication table (SET with TTL) to achieve effectively-exactly-once processing.

WebSocket push will be served by a lightweight bridge that reads from the same stream and fans out to connected clients via Redis Pub/Sub or a dedicated stream consumer group.

---

## Consequences

### Pros

1. **Zero new infrastructure.** Redis is already deployed, monitored, and operated by the team. No new cluster, no new backup strategy, no new firewall rules, no new TLS certificates to manage.
2. **Fast time-to-value.** A senior engineer familiar with Redis can have a working `XADD` → `XREADGROUP` → `XACK` pipeline in production within 2–3 days. The first week delivers decoupled async dispatch with retry. The second week adds the dead-letter queue and monitoring.
3. **Adequate throughput.** A single Redis instance handles 100k+ ops/s on modest hardware. At current peak (500 req/s) and 10× target (~5,000 req/s, each producing 1–3 notification events), the load is comfortably inside Redis's sweet spot. Redis Cluster scales horizontally if needed.
4. **At-least-once delivery is innate.** Consumer groups (XREADGROUP with PEL) guarantee that unacknowledged messages are redelivered to another consumer in the group. This maps directly onto retry + exponential backoff logic.
5. **Effectively-exactly-once is achievable.** Billing events carry an idempotency key; consumers `SADD` the key (with TTL) before processing and skip on collision. This is a well-understood pattern that the team can implement correctly without platform-level transaction support.
6. **Simpler WebSocket bridge.** The stream serves as a unified event log that both HTTP-based consumers and WebSocket fan-out consumers can read from the same consumer group mechanism.
7. **Operational simplicity.** No JVM tuning, no broker rebalancing, no ZooKeeper/KRaft migration. The team's existing Redis playbooks (sentinel failover, RDB/AOF persistence, `maxmemory` policies, CloudWatch metrics) apply unchanged.
8. **Lower cognitive load for hiring.** Redis experience is far more common among Python/Flask engineers than Kafka experience. The learning curve for Redis Streams is measured in hours, not weeks.

### Cons

1. **Memory-bound retention.** Streams live in RAM. Long retention of large volumes of messages is expensive. Mitigation: use `MAXLEN ~ N` to cap stream length to a recent window (e.g., last 100k messages) and archive older events to S3 for audit/replay. Billing events get longer retention because volume is low.
2. **No native exactly-once.** Unlike Kafka's transaction API (which itself has caveats and complexity), Redis Streams offer no transactional producer → consumer exactly-once guarantee. The team must implement consumer-side idempotency for billing events. Mitigation: this is a well-known pattern; the idempotency key `SADD` with TTL adds ~15 lines of code per critical handler.
3. **No automatic consumer rebalancing.** When a consumer joins or leaves a group, partition assignment does not rebalance automatically. Mitigation: at current scale a small, stable worker pool (3–6 consumers) is simple to configure manually. If the team reaches the scale where dynamic rebalancing matters, they can adopt Redis Cluster, which shards by key and effectively partitions the stream.
4. **Single-threaded bottleneck concern.** The stream write path on a single Redis instance is single-threaded. At 10× growth (~5,000 req/s × 2 events = ~10,000 XADD/s) this is still well within Redis's ~100k ops/s capability. If events per request grow disproportionately, Redis Cluster shards the load across cores.
5. **Not an event store.** Redis Streams do not support the kinds of long-term, queryable event replay that Kafka does. If the team later needs an event-sourced architecture or a full audit log with indefinite retention, they may need to add Kafka or a purpose-built store. Mitigation: archive completed notifications to S3/PostgreSQL as a structured log; the stream is a transient routing buffer, not a permanent record.

---

## Alternatives Considered

### Apache Kafka

**Why it was considered:** Kafka is the industry standard for async event pipelines. It offers high throughput (millions of msg/s), configurable retention on disk, strong partition-level ordering, consumer groups with automatic rebalancing, and a transaction API supporting exactly-once semantics.

**Why it was rejected:**

The rejection is driven by **team constraints**, not technical capability. Kafka would do the job exceptionally well — but under conditions the team does not have.

- **No in-house Kafka expertise.** A team of 6 with zero Kafka experience would need to learn broker configuration, topic partitioning, replication factor sizing, ZooKeeper or KRaft management, JVM heap tuning, `log.retention.bytes` vs `log.segment.bytes`, partition leader election, ISR configuration, consumer rebalancing protocol, and the quirks of the `confluent_kafka` Python client (which wraps `librdkafka` in C and has a non-trivial compile-time dependency chain). This learning curve directly conflicts with the ≤2-week time-to-value constraint.
- **Operational overhead.** Kafka is a distributed system that demands operational attention: disk sizing (Kafka is I/O-bound, wants dedicated SSDs), monitoring (lag per consumer, ISR state, broker health), partition rebalancing during rolling upgrades, OS page cache tuning. For a team with no dedicated infrastructure engineer, this maintenance tax is non-trivial.
- **Self-hosted Kafka is not free.** AWS MSK starts at ~$0.15/hr per broker (3 brokers = ~$300/month) at the smallest tier. While not Confluent Cloud's pricing, it's an additional monthly cost for something Redis already handles at current and 10× scale. Self-hosting Kafka on EC2 adds management time that is clearly costed in engineering hours.
- **Overkill for the load profile.** At ~500 req/s peak (10× = ~5,000 req/s), Kafka is over-provisioned by roughly two orders of magnitude. The operational complexity is not justified by the throughput requirement.
- **Exactly-once is still hard.** Kafka's EOS via transactions and idempotent producers is notoriously tricky to implement correctly, especially in the Python ecosystem where `confluent_kafka` wraps a C library. For a team new to Kafka, it's as likely to cause subtle correctness bugs as Redis Streams + idempotent consumers.

**When Kafka would become the right choice:** If the event volume grows beyond ~100,000 msg/s, or if the team needs indefinite, queryable event replay (event sourcing), or if the org grows a dedicated infrastructure/platform team with Kafka expertise, a migration to Kafka would be justified. At that point Redis Streams can serve as an edge buffer feeding into a Kafka topic, preserving the investment.

### Amazon SQS + SNS

**Why it was considered:** Fully managed, no operational overhead, at-least-once delivery, DLQ support, FIFO queues for exactly-once.

**Why it was rejected:** SQS FIFO has a hard throughput cap of 300 transactions/s (batch of 10 = 3,000 msg/s), which conflicts with the 10× growth target. SQS standard has at-least-once but can deliver duplicates. Neither provides ordered broadcast to multiple consumer groups (WebSocket + email + webhook) without SNS fan-out, adding another moving part. Lock-in to AWS is acceptable but the throughput ceiling on FIFO queues is a hard blocker for a system targeting 10× growth.

### RabbitMQ

**Why it was considered:** Mature, well-understood AMQP broker. Supports consumer acknowledgements, DLQs, dead-letter exchanges, and retry with TTL.

**Why it was rejected:** Would require new infrastructure and operational knowledge (Erlang VM tuning, queue type selection — quorum vs classic vs streams). The team has no Erlang/Elixir experience. RabbitMQ's stream plugin (optional) competes with Redis Streams but with lower throughput and less Python ecosystem support. Compared to Redis Streams, it offers no advantage for this use case and introduces more operational surface area.
