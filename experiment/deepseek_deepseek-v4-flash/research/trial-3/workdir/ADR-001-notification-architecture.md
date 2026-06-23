# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

---

## Context

We operate a SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak). The current notification subsystem sends emails and webhooks synchronously inside the HTTP request cycle. This has caused:

- **Request timeouts** — average 800ms notification latency, spiking to 8s during peak hours
- **Silent failures** — email provider or webhook downtime drops notifications with no retry or dead-letter queue
- **Cascading failures** — two incidents this year where a slow webhook exhausted the connection pool, taking down unrelated request paths
- **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") lack exactly-once semantics

### Requirements

1. Decouple notifications from the HTTP request cycle (async processing)
2. Support retry with exponential backoff
3. At-least-once delivery for general notifications; exactly-once for billing events
4. Enable real-time WebSocket push within two quarters
5. Handle 10x traffic growth (~5,000 req/s peak) without re-architecting

### Constraints

- Engineering team of 6 (3 senior, 3 mid-level); no dedicated infrastructure engineer
- Redis already in production for session storage and rate limiting
- Zero Kafka experience on the team
- Deliverable value within 2 weeks of setup/migration work
- Modest budget — managed Confluent Cloud is not affordable at full scale
- Exactly-once semantics required for billing notifications

---

## Decision

**Use Redis Streams as the notification message broker.**

Redis Streams provides the asynchronous decoupling, consumer group semantics, and persistence guarantees we need, without introducing new infrastructure or requiring the team to learn an entirely new system.

We will implement three consumer groups on a single notification stream, or partitioned by stream per notification type (email, webhook, WebSocket). A worker pool (backed by Celery or a simple `asyncio` task group) reads from the stream, dispatches notifications, and acknowledges entries on success. Failed deliveries are re-queued by the consumer group's pending-entry list mechanism with exponential backoff via `XCLAIM` after a visibility timeout. Billing notifications achieve exactly-once processing through consumer-side idempotency (see Consequences).

---

## Consequences

### Advantages

**Zero new infrastructure.** Redis is already deployed, monitored, and backed up. Adding Streams requires no new VMs, no new stateful services, and no change to the deployment pipeline. The first consumer worker can be written and deployed in a day.

**Familiar operational model.** The team already handles Redis key eviction, memory monitoring, and failover. Stream management is a small delta of operational knowledge — `XADD`, `XREADGROUP`, `XACK`, `XCLAIM`, `XTRIM` — all accessible via `redis-cli` and the existing Python `redis` library.

**Adequate throughput headroom.** A single Redis instance handles 100k+ operations per second. Our current peak is 500 req/s; at 10x growth it is 5,000 req/s, with each request producing 1-3 notification events. At worst (~15k events/s), we are at 15% of a single Redis node's capacity. Partitioning into per-type streams or sharding across Redis Cluster nodes is future work, not immediate necessity.

**Native consumer groups.** Redis Streams consumer groups map directly to our worker pool model. Each consumer in a group receives a subset of stream entries. The `XPENDING` / `XCLAIM` mechanism provides automatic re-delivery of unacknowledged messages on worker failure, giving us at-least-once delivery with minimal code.

**Exactly-once semantics via consumer idempotency.** Redis Streams assigns a unique, monotonically increasing ID to each entry (`<timestamp>-<sequence>`). For billing notifications, the consumer records this ID in a PostgreSQL `processed_notifications` table (with a unique constraint on `stream_entry_id`) inside the same transaction that applies the billing action. If a notification is re-delivered after a crash, the consumer skips it because the ID already exists. This gives exactly-once *processing* on top of at-least-once *delivery* — a well-understood pattern that requires no broker-level transactional support.

**Natural path to WebSocket push.** Redis Pub/Sub or the same Streams mechanism can feed a WebSocket gateway process that pushes notifications to connected clients. The existing Redis cluster is the coordination point; no Kafka-to-WebSocket bridge is needed.

**Retry and dead-letter without extra infrastructure.** The consumer group's pending-entry list acts as an in-flight retry queue. After N failed attempts (tracked via a consumer-side counter written to a separate Redis hash or embedded in a stream metadata field), entries can be moved to a dead-letter stream (`XADD deadletter:notifications * ...`). A separate dashboard worker can inspect and manually replay dead-letter entries.

### Disadvantages

**Memory-bound retention.** Redis stores streams in RAM. Without `XTRIM` (or `MAXLEN` policy), an unbounded stream grows until it exhausts memory. We must set `MAXLEN ~ 100000` on the notification stream to bound memory to ~100-200 MB (assuming ~2 KB per entry). This limits how far back we can replay history — messages older than the trim window are lost. For billing audit trails, we persist notification delivery status to PostgreSQL; the stream is a transient work queue, not an event store.

**No native partitioning for parallelism beyond a single stream.** Consumer groups distribute entries round-robin across consumers, but all consumers read from the same Redis node. At very high throughput (100k+ events/s), a single stream becomes a bottleneck. Mitigation: partition by notification type into separate streams (`stream:email`, `stream:webhook`, `stream:websocket`), each with its own consumer group. This is a design choice, not a limitation — Kafka's partitions exist for the same reason.

**No Kafka Connect ecosystem.** Integrating with external systems (S3, Elasticsearch, data warehouses) requires building custom consumers rather than using pre-built Kafka Connect connectors. For our current scope (email, webhook, WebSocket), this is irrelevant — we control all endpoints. If future analytics pipelines need notification events, we can sink them to PostgreSQL or S3 via a custom consumer.

**No built-in stream processing.** Kafka Streams and KSQL enable joining, aggregating, and transforming streams inside the broker ecosystem. Redis Streams has no equivalent — all processing lives in application code. For our use case (dispatch and retry), application-code processing is simpler and more debuggable than a stream-processor topology. If we need complex event processing later, we add it in Python, not in the message layer.

---

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for high-throughput, persistent, partitioned event streaming. Its log-structured storage provides disk-backed retention measured in days or weeks, native partitioning for horizontal scaling, and the Kafka Streams API for complex stream processing. The transactional producer/consumer API provides broker-enforced exactly-once semantics.

We reject Kafka for this project because:

- **Operational overhead is disproportionate.** A production Kafka cluster requires KRaft or ZooKeeper, broker tuning (segment size, replication factor, ISR configuration), monitoring (consumer lag, under-replicated partitions), and careful capacity planning. With 6 engineers, no infrastructure specialist, and no Kafka experience, this is a significant operational burden.
- **2-week delivery is infeasible.** Standing up a Kafka cluster, securing it, integrating with our Python monolith (confluent-kafka or kafka-python), and tuning for our workload would take 2-4 weeks before a single notification flows through the system. Redis Streams can be production-ready in 2 days.
- **Overkill at our scale.** Kafka excels at millions of messages per second across hundreds of partitions. Our 5,000 req/s target is three orders of magnitude below that — Redis Streams handles it comfortably with a fraction of the complexity.
- **Cost.** A 3-broker Kafka cluster on AWS (m6i.large, including EBS storage) costs ~$500-800/month. While not prohibitive, it is a new line item for capability we do not need. Managed Confluent Cloud adds 2-3x more. Redis Streams adds zero cost — we already run Redis.
- **Team learning curve.** Every engineer would need to learn Kafka's partitioning model, consumer group rebalancing, offset management, and exactly-once configuration. With Redis Streams, every engineer already understands the underlying data structure (the stream, consumer groups, pending entries).
- **Exactly-once via Kafka is not free.** Kafka's exactly-once semantics require the idempotent producer (`enable.idempotence=true`) and the transactional API (`beginTransaction()` / `commitTransaction()`), which introduce their own complexity — transaction coordinator failures, zombie fencing, and producer timeouts. For our billing-notification use case, the consumer-side idempotency pattern (unique stream entry ID + dedup table) is simpler, equally correct, and independent of broker features.

**Kafka becomes the right choice** if our event volume exceeds 100k messages/second, if we need event sourcing with weeks-long replay windows, or if we grow a dedicated platform team to operate the cluster. None of those conditions hold today.

### Amazon SQS / SNS

SQS provides managed message queuing with exactly-once delivery (via FIFO queues), dead-letter queues, and no infrastructure to manage. SNS enables pub/sub fan-out. This is a viable alternative with zero ops overhead.

We reject SQS/SNS because:

- **Vendor lock-in is expensive at scale.** SQS pricing ($0.40/million requests + data transfer) becomes significant at 10x growth. Our estimated 15M-45M events/month at 10x growth would cost ~$6-18/month in requests plus data transfer costs — modest, but recurring and growing with usage. More importantly, the SQS consumer model (long-polling, 256KB message size limit) constrains our WebSocket push roadmap: pushing real-time updates through SQS requires a bridge component, whereas Redis Pub/Sub plus Streams is a single system.
- **No consumer groups.** SQS does not support Kafka-like consumer groups. Each queue consumer competes for messages; scaling requires more queue shards or a custom partitioning layer. Redis Streams consumer groups give us this natively.
- **Retry flexibility is limited.** SQS's built-in retry (redrive policy) is queue-level, not message-level. Redis Streams gives us fine-grained control: per-message visibility timeout, per-message retry count, and a programmable dead-letter stream.
- **We already run Redis.** Adding SQS means managing a second message-passing system alongside the existing Redis cluster. Redis Streams consolidates on one.

### PostgreSQL LISTEN/NOTIFY + Job Table

The simplest approach: write notification jobs to a `notifications` table in PostgreSQL, have a background worker poll for pending jobs, and use `LISTEN`/`NOTIFY` for wake-up signaling. This avoids any new technology.

We reject this because:

- **No consumer groups.** Multiple worker processes must coordinate via `SELECT ... FOR UPDATE SKIP LOCKED`, which adds contention and complexity at scale. Redis Streams consumer groups handle this at the broker level.
- **Polling overhead.** At 10x growth, polling a jobs table every N seconds wastes database cycles. `LISTEN`/`NOTIFY` helps, but PostgreSQL notifications are transient — if no listener is connected, the notification is lost.
- **No native retry or dead-letter.** Retry logic, backoff, and dead-letter routing would all be hand-rolled SQL and application code. Redis Streams provides these primitives (pending list, `XCLAIM` timeout, separate dead-letter streams) out of the box.
- **DB as message bus is an anti-pattern.** PostgreSQL is our source of truth for business data. Using it as a message queue adds I/O pressure, table bloat from unprocessed rows, and vacuum overhead that Redis avoids by design.

---

## Recommendation

**Redis Streams is the correct choice for our context.** It solves the immediate problems (synchronous blocking, silent failures, cascading faults) with minimal new infrastructure, maps well to our team's existing Redis expertise, and leaves a clean path to WebSocket push and future scaling through stream partitioning. Kafka can be revisited when — and if — our event volume outgrows a single Redis node or our team has dedicated ops bandwidth to run it.

### Migration Milestones

| Milestone | Timeframe | What ships |
|-----------|-----------|------------|
| P0 — Async decoupling | Week 1-2 | Consumer group on `stream:notifications`, retry with `XCLAIM`, dead-letter stream |
| P1 — Exactly-once billing | Week 3 | Idempotency table in PostgreSQL, billing notifications first |
| P2 — WebSocket push | Weeks 6-8 | WebSocket gateway consuming `stream:websocket`, Redis Pub/Sub for real-time fan-out |
| P3 — Partitioned streams | Week 12+ | Split `stream:notifications` into `stream:email`, `stream:webhook`, `stream:websocket` per-type consumer groups |

Each milestone is independently shippable and delivers user-visible reliability improvements.
