# ADR-001: Use Redis Streams for Async Notification Processing

**Status:** Proposed

---

## Context

The Notifier subsystem (emails and webhooks for task updates, assignments, completions) runs synchronously inside the Flask HTTP request cycle. As the platform has grown to 85,000 MAU with ~2M tasks/month and 500 req/s peak, this coupling has caused:

- **Request timeouts** — average notification latency is 800ms, spiking to 8s at peak. Users see slow page loads and timeouts for non-cacheable mutations.
- **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry, no dead-letter queue, and no operator alert.
- **Cascading failures** — two incidents this year where a slow webhook endpoint consumed all available database/HTTP connections, taking down unrelated features.
- **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed", "invoice overdue") must be delivered exactly once. The current system has no mechanism for this.

We need to decouple notifications from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (and exactly-once for billing events), support future real-time WebSocket push, and handle 10x traffic growth without re-architecting.

**Team & infrastructure constraints:**

- 6-person engineering team (3 senior, 3 mid-level) with no dedicated infrastructure engineer
- No Kafka experience on the team today
- Already running Redis in production for session storage and rate limiting
- Must deliver value within 2 weeks of setup work
- Modest budget — cannot afford managed Confluent Cloud at full scale
- Must maintain exactly-once semantics for billing notifications

---

## Decision

**Use Redis Streams** as the async message broker for the notification subsystem.

Producers (the Flask app on task update) will `XADD` notification events to a Redis stream. Consumer workers in a consumer group (`XREADGROUP`) will process, `XACK` on success, and rely on the PEL (Pending Entries List) for redelivery of unacknowledged messages. Billing-critical events will carry an idempotency key stored alongside the delivery record in PostgreSQL, providing exactly-once semantics at the point of external delivery.

### Why Redis Streams

**1. Zero new infrastructure.** Redis is already in production. Adding streams uses the same servers, the same backup procedures, and the same monitoring — no new deploy pipelines, no new security reviews, no new paging alerts.

**2. Immediate team productivity.** Every engineer knows the Redis CLI, the Redis Python client (redis-py), and basic operations. The learning curve is hours, not weeks. The stream-based consumer group model (`XREADGROUP`, `XACK`, `XPENDING`) maps cleanly onto the problem: claim pending messages, process, acknowledge. No partition strategy, no log compaction, no ZooKeeper/KRaft quorum to reason about.

**3. Time-to-value under 2 weeks.** A working producer → consumer pipeline with retry and dead-letter routing can be implemented in 3–5 days. The remaining time goes to testing, idempotency key infrastructure for billing events, observability, and the WebSocket migration plan. Kafka would consume the full 2 weeks in setup alone (cluster provisioning, schema registry, learning and debugging a new stack).

**4. Sufficient throughput.** Redis Streams on modest hardware handles 100k+ operations per second. At 500 req/s peak (5,000 at 10x growth), the notification stream is well within Redis's single-threaded throughput envelope. A single Redis instance handles this load with room to spare; clustering is not needed.

**5. Natural path to WebSocket push.** Redis Pub/Sub already fits the WebSocket bridge pattern. Streams can be consumed and fanned out over Pub/Sub with negligible latency (<1ms). A dedicated subscriber process reads from the stream and publishes to a channel that the WebSocket server subscribes to — no additional broker needed.

**6. At-least-once delivery is built in.** The PEL mechanism tracks every unacknowledged message per consumer. Failed consumers get their messages reassigned to another consumer after a configurable timeout (`XPENDING` + `XCLAIM`). This maps directly to the required retry-with-backoff pattern.

**7. Exactly-once via application-layer idempotency.** Neither Redis Streams nor Kafka provides exactly-once delivery *to external systems* (email provider API, webhook endpoint) without application-level idempotency. Kafka's EOS (Exactly-Once Semantics) guarantees exactly-once within the Kafka cluster itself — producer-to-broker and broker-to-broker. It does not extend to external HTTP calls. The engineering requirement is identical either way: attach an idempotency key to the event, store it in PostgreSQL on first successful delivery, and skip/ignore duplicates. Redis Streams carries this key as a stream field just as naturally as Kafka carries it in the record headers.

---

## Consequences

### Pros

| Consequence | Detail |
|---|---|
| **Fastest path to value** | Production-ready notification pipeline in days, not weeks. |
| **Lowest operational burden** | No new infrastructure. Redis is already monitored, backed up, and understood by on-call. |
| **Team velocity** | No Kafka learning curve. The full engineering team can contribute to and review the notification code immediately. |
| **Natural WebSocket integration** | Redis Pub/Sub bridges into the existing stack without a second message broker. |
| **Cost-effective** | No additional EC2 or MSK spend. Existing Redis capacity absorbs the notification workload. |
| **Graceful scale** | Redis Streams handles 10x traffic on a single instance. Clustering (Redis Cluster) is a known migration path if needed. |

### Cons

| Consequence | Mitigation |
|---|---|
| **No native exactly-once for external delivery** | Application-level idempotency keys in PostgreSQL. Needed anyway — Kafka's EOS does not extend past the broker. |
| **Memory-bound retention** | Streams are memory-resident. Long backlogs could evict session data. | Use `MAXLEN ~` with consumer lag monitoring. Set a retention cap that keeps the stream within 20% of Redis memory. Alert on consumer lag exceeding that cap. Notifications are processed in seconds/minutes, not days — retention pressure is minimal. |
| **Single-node bottleneck at extreme scale** | If traffic exceeds 50,000 req/s sustained, Redis could saturate a single core. | Redis Cluster shards streams by hash slot. This is a known migration path, not a rebuild. At our 5,000 req/s 10x target, no clustering is needed. |
| **Weaker durability guarantees than Kafka** | Redis is CP under partition (minority partitions reject writes). During a Redis failover, unacknowledged stream messages could be lost. | Enable Redis AOF (append-only file) with fsync every second. The consumer group state is replicated. For billing notifications, the idempotency key + PG record is the source of truth; a lost stream message still results in at-least-once (not at-most-once) because the producer retries on detected failure. |
| **Broader ecosystem is smaller** | Fewer third-party tools, connectors, and managed services exist for Redis Streams vs Kafka. | For our scope (Python consumers, PostgreSQL persistence, WebSocket bridge), we need zero connectors. The ecosystem gap is irrelevant. |

---

## Alternatives Considered

### Apache Kafka

Rejected for this team and scale.

**Why it's attractive for the general case:** Kafka provides append-only log semantics with configurable disk-based retention, true linearizable ordering within a partition (under `acks=all` + `min.insync.replicas`), superior throughput at hyperscale (millions of messages/second), and a mature ecosystem of connectors. The exactly-once semantics (EOS) between producers and brokers are industry-leading *within the Kafka cluster*.

**Why it's wrong here:**

| Criterion | Assessment |
|---|---|
| **Operational complexity** | A production Kafka cluster requires ZooKeeper or KRaft quorum management, JMX monitoring, partition rebalancing, consumer-lag tooling, and steady tuning (broker heap, page cache, replication throttling). For a 6-person team with no dedicated infra engineer, this is a significant tax on every sprint. |
| **Setup timeline** | Provisioning, securing, tuning, and validating a Kafka cluster — plus teaching the team Kafka's consumer model — would consume the full 2-week budget before a single notification is processed. Redis Streams delivers in days. |
| **Team knowledge** | Zero Kafka experience on the team. Every incident, review, and performance investigation requires context-switching into an unfamiliar system. Redis is known by everyone. |
| **Cost** | Self-managed Kafka on EC2 (minimum 3 brokers + ZooKeeper nodes) costs more than running a Redis instance. Managed MSK starts at ~$0.50/hr (~$360/month) for a minimal cluster, plus storage and data-transfer costs. This is not budget-breaking but is unnecessary spend when Redis handles the load. |
| **Overkill at current scale** | Kafka excels at 100k+ msg/s with multiple consumers doing log replay, stream processing, and long-term retention. Our workload is 500–5,000 notifications/s, single consumer group, sub-minute processing latency. Kafka is optimized for a problem we don't have. |
| **Exactly-once misconception** | Kafka's EOS guarantees atomic producer-to-broker writes and exactly-once stream processing *within Kafka* (Kafka Streams). It does not make an HTTP POST to a webhook or an SMTP call to an email provider idempotent. The application-layer idempotency key is required either way. Switching to Kafka does not eliminate this work. |

**Verdict:** Kafka is the right choice for a larger engineering organization (15+ engineers, dedicated platform/infra function) handling 100k+ events/second with 30+ day retention requirements and multiple heterogeneous consumer groups replaying from arbitrary offsets. For this team, at this scale, and under these constraints, it is the wrong tool.

---

*Prepared for the engineering team. Decision is open for discussion and amendment as requirements evolve.*
