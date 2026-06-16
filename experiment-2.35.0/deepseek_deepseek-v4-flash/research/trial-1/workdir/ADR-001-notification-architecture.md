# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

## Context

The notification subsystem in our project management SaaS sends emails and webhooks on task events (update, assignment, completion). It currently runs synchronously inside the HTTP request cycle, causing three concrete problems:

- **Request timeouts:** Average response latency of 800ms, spiking to 8s during peak hours, because the response waits for external API calls (email provider, webhook endpoints).
- **Silent failures:** When an external provider is unreachable, the notification is dropped. No retry, no dead-letter queue.
- **Cascading failures:** Two incidents in the past year where a slow webhook endpoint consumed all available connections in the pool, taking down unrelated features.
- **No delivery guarantees:** Billing-critical notifications ("trial expired", "payment failed") must be delivered at least once (exactly once where feasible), but the current system provides none of these guarantees.

**Target requirements:**
1. Decouple notification dispatch from the HTTP request cycle.
2. Support retry with exponential backoff and a dead-letter mechanism.
3. Guarantee at-least-once delivery for billing events; exactly-once where feasible.
4. Support real-time WebSocket push within two quarters.
5. Handle 10x traffic growth (~5,000 req/s peak, ~20M tasks/month) without re-architecting.

**Team and infrastructure constraints:**
- Engineering team of 6 (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis is already deployed in production for session storage and rate limiting.
- No team member has production Kafka experience.
- The solution must deliver value within 2 weeks of setup and migration.
- Budget is modest — managed Confluent Cloud is not an option at full scale.
- The architecture must support exactly-once semantics for billing notifications.

## Decision

**Use Redis Streams.**

Adopt Redis Streams as the message backbone for the notification subsystem. Notifications produced during the HTTP request cycle are written into Redis Streams; one or more background worker processes consume from the stream, dispatch the email or webhook, and acknowledge the message on success. Failed messages are retried from the Pending Entry List (PEL) with exponential backoff and eventually moved to a separate dead-letter stream.

### Architecture Outline

```
HTTP Request → Flask handler → XADD to Redis Stream (non-blocking, ~1ms)
                                       │
                              ┌────────▼────────┐
                              │   Redis Stream   │
                              │  (Consumer Group)│
                              └────────┬────────┘
                                       │
                         ┌─────────────┴──────────────┐
                         │  Worker (XREADGROUP)        │
                         │  Dispatch email/webhook     │
                         │  XACK on success            │
                         │  PEL retry on failure       │
                         └─────────────┬──────────────┘
                                       │
                              ┌────────▼────────┐
                              │  Dead-Letter     │
                              │  Stream (XADD)   │
                              └─────────────────┘
```

## Consequences

### Advantages

- **Zero new infrastructure.** Redis is already running in production. Adding streams requires no new servers, no new deployment pipelines, no new credential management. This alone saves 1–2 weeks of setup time versus any solution requiring a new backing store.

- **Familiarity.** The team already manages Redis. The `redis-py` library is a dependency today. Learning Redis Streams (`XADD`, `XREADGROUP`, `XACK`, `XPENDING`) requires understanding a few commands, not an entire distributed system paradigm. A senior engineer can spike a working prototype in a day.

- **Fast path to value.** A minimal implementation (write to stream in the Flask handler, one worker reading the stream and dispatching) can ship to production within the first week. Retry logic, dead-letter, and monitoring can be added incrementally in subsequent weeks.

- **Natural fit for WebSocket push.** The two-quarter roadmap for WebSocket push aligns well with Redis Pub/Sub, which can be layered on the same Redis instance alongside Streams. We can publish a WebSocket event on the same Redis connection that writes the stream entry. Frameworks like Socket.IO with a Redis adapter integrate directly.

- **Consumer groups with PEL.** Redis consumer groups provide exactly the mechanism we need: workers pick up unclaimed messages, the PEL tracks unacknowledged deliveries, and `XPENDING` lets us detect stalled consumers. Combined with a retry counter in the message payload, this gives us retry with exponential backoff and a dead-letter threshold without writing a separate queuing system.

- **Throughput headroom.** At 500 req/s peak (~1 notification per request average), we are well within Redis Streams' capability of 100k+ small messages per second. At 10x growth (~5,000 req/s), a single Redis instance still handles the load with room to spare. If needed, Redis Cluster extends that further.

- **At-least-once delivery for billing.** The PEL guarantees that a message stays in the pending list until a consumer explicitly acknowledges it (XACK). If a consumer crashes mid-dispatch, another consumer picks it up after the pending-timeout. Combined with idempotency keys on the consumer side (checking a dedup index in Redis before sending), this achieves exactly-once processing for billing notifications.

### Disadvantages

- **Memory-bound retention.** Redis Streams live in memory (with optional persistence via RDB/AOF). Unlike Kafka's disk-based log, we cannot cheaply retain months of historical messages. At our current volume, even storing 7 days of notifications (2M × 7 = 14M entries at ~500 bytes each = ~7 GB) fits comfortably in a 16 GB Redis instance, but long-term archival requires a separate pipeline to PostgreSQL or S3. This is an acceptable trade-off: we need retention for replay and debugging, not for replaying months of data.

- **No built-in exactly-once semantics.** Redis Streams do not have Kafka's transactional producer API for atomic writes across partitions. Exactly-once must be built at the application layer: idempotency keys + dedup + atomic updates. This is achievable and well-understood (we would implement it for Kafka too), but it is more code we own.

- **Smaller ecosystem.** Kafka has a richer ecosystem of connectors, stream processors (Kafka Streams, ksqlDB), monitoring (Burrow, Cruise Control), and managed offerings. Redis Streams has fewer purpose-built tools. For a 6-person team building a notification subsystem, this matters less than operational simplicity — we don't need KSQL, we need a worker that reads a stream and sends HTTP requests.

- **Scaling beyond a single Redis instance requires cluster mode.** At current and 10x projected load, a single Redis instance is sufficient. If growth exceeds that, switching to Redis Cluster adds operational complexity (client-side sharding, cross-slot limitations). In practice, this is a future concern well beyond the 10x target.

- **No partition scaling model.** Kafka's partition model allows independent scale of parallelism (more consumers per partition) and data distribution (more partitions). Redis Streams distribute messages across consumers in a group, but the stream itself lives on a single Redis node in non-cluster mode. For a notification workload, this is not a bottleneck at our scale.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for event streaming. It offers disk-based log retention, automatic consumer group rebalancing, partition-based parallelism, and a transactional API for exactly-once semantics. For a system processing millions of events per day with strong durability guarantees, Kafka is a proven choice.

**Why Redis Streams wins for us:**

- **Operational complexity mismatch.** A production Kafka deployment requires at least 3 broker nodes and 3 ZooKeeper nodes (or KRaft controllers) for fault tolerance. This means standing up 6 new servers, configuring them, monitoring JMX metrics, managing partition rebalancing, and learning Kafka-specific failure modes (leader election, ISR management, log compaction). For a team of 6 with no Kafka experience and no dedicated infra engineer, this is a 4- to 6-week investment before delivering any value to users.

- **Setup timeline violates the 2-week constraint.** Even with managed Kafka (Confluent Cloud), the team would need to learn the Kafka API, `confluent-kafka-python` client semantics (delivery callbacks, exactly-once config, consumer rebalance listeners), and wire up monitoring from scratch. A self-hosted Kafka setup cannot realistically be production-ready within 2 weeks. Redis Streams, by contrast, can ship a working prototype in days because the infrastructure already exists.

- **Cost.** Self-hosted Kafka requires a minimum of 6 EC2 instances (3 brokers + 3 ZooKeeper). At `m6i.large` (~$70/month each), that is ~$420/month in base infrastructure plus EBS storage. Confluent Cloud's basic tier starts at a few hundred dollars per month and scales up rapidly with throughput. Redis Streams costs zero incremental infrastructure — we already pay for the Redis instance.

- **Throughput overprovisioning.** Kafka shines at 100k+ messages/second with sustained high throughput. Our workload is 500 req/s peak. Kafka's strengths (brokered storage, compaction, tiered storage) solve problems we do not have. Meanwhile, its weaknesses (client complexity, operational surface area, rebalancing-induced unavailability) are costs we would pay upfront.

- **WebSocket integration adds complexity.** Pairing Kafka with WebSocket push requires an additional bridging service (e.g., Kafka Connect + WebSocket sink, or a service consuming Kafka and publishing via a WebSocket server). With Redis, the stream and the pub/sub channel live on the same instance — a single `publish` call alongside the `XADD` gives us WebSocket push for free.

- **Exactly-once via Kafka transactions is the wrong tool for this job.** Kafka's exactly-once semantics depend on transactional producers, idempotent consumers, and atomic writes to an output topic. Setting this up correctly is notoriously subtle (transactions time out, zombie fencing, coordinator failures). For a 6-person team, building idempotency in the application layer (a dedup key in Redis, a unique-notification-ID per event) is simpler and equally correct for our use case. We would implement idempotency regardless of the message broker choice — Kafka's transactions do not eliminate that need.

**When Kafka would be the right choice:** If our requirements included (a) retaining a multi-year, replayable event log for auditing or analytics, (b) processing a sustained >50K events/second, or (c) integrating with Kafka-native stream processors (Kafka Streams, ksqlDB) for complex event processing. None of these are current or projected requirements.

## Migration Path

The decision for Redis Streams does not preclude Kafka later. We will abstract the message bus behind a `NotificationBroker` interface with `produce(event, topic)` and `consume(topic, handler)` methods. The initial implementation wraps Redis Streams; if growth or requirements eventually justify Kafka, a second implementation swaps the backend with no changes to the notification logic or HTTP handler.
