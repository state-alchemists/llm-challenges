# ADR-001: Asynchronous Notification Subsystem — Redis Streams vs. Apache Kafka

**Status:** Proposed

---

## Context

The Notifier subsystem (emails and webhooks for task updates, assignments, completions) runs synchronously inside the Flask HTTP request cycle. This causes three classes of failure:

1. **Latency spikes.** Average response time is 800 ms and peaks at 8 s during business hours because the request thread blocks on external SMTP/webhook calls.
2. **Silent data loss.** A downed email provider or webhook endpoint drops the notification with no retry, no dead-letter queue, no operator alert.
3. **Cascading outages.** A slow webhook endpoint exhausted the connection pool twice this year, taking down the entire web application including unrelated features.

The system must be re-architected so that the HTTP request enqueues a notification event and returns immediately; a background worker processes the event asynchronously with retry, backoff, and delivery guarantees.

### Current platform characteristics

| Dimension | Value |
|---|---|
| Monthly active users | 85,000 |
| Tasks created / month | ~2 million |
| Peak request rate | ~500 req/s |
| Backend | Python/Flask monolith (~50 kLOC) |
| Database | PostgreSQL (primary + 1 read replica) |
| Web tier | 4 servers, nginx, AWS |
| Existing Redis usage | Session storage, rate limiting |
| Team | 6 engineers (3 senior, 3 mid), no dedicated infra |
| Existing Kafka experience | None |

### Key requirements

- Decouple notification delivery from the HTTP request cycle.
- At-least-once delivery for billing events (trial expiry, payment failures, plan changes).
- Retry with exponential backoff and a dead-letter queue.
- Path to real-time WebSocket push within two quarters.
- Survive 10× traffic growth without a re-architecture.
- Deliver value within two weeks; the team cannot spend months learning new infrastructure.

---

## Decision

**Adopt Redis Streams** as the notification backbone.

### Justification

**The team already runs Redis.** It is in production today for session storage and rate limiting. Adding Streams requires no new servers, no new daemon to learn, and no new security review. The incremental operational cost is effectively zero — a modest bump in Redis memory and one additional consumer process on an existing host.

**The throughput requirement is well within Redis Streams' capacity.** At 500 req/s peak today, even 10× growth produces 5,000 events/s. A single `cache.r6g.large` or `cache.m6g.large` Elasticache node handles sustained writes at 10–20× that rate. Kafka's horizontal partitioning advantage does not matter at this scale.

**Consumer groups solve the core problems natively:**
- **Parallel processing.** Multiple worker processes can consume from the same stream as a consumer group. Each event goes to exactly one consumer, matching the webhook fan-out model.
- **Acknowledgement and retry.** Workers acknowledge (`XACK`) events after successful delivery. Unacknowledged events reappear via `XPENDING` and can be claimed (`XCLAIM`) by another worker. This maps directly to the retry-with-backoff requirement.
- **Dead-letter queue.** Events that exceed a retry threshold are moved to a separate stream (the DLQ). The pattern is straightforward and well-documented — no additional infrastructure required.

**Exactly-once semantics are achievable at the application layer.** Redis Streams offers at-least-once delivery natively (a consumer receives an event; if it crashes before acking, another consumer replays it). Billing-critical events get idempotency keys stored alongside the event payload; the consumer checks for a duplicate before processing. This is the same approach used in practice on top of Kafka unless Kafka's transactional API is engaged, which adds its own complexity.

**The WebSocket push requirement fits naturally.** A separate consumer group on the same stream can feed a WebSocket relay process. Redis Pub/Sub can also serve as a real-time notification bus, keeping the infrastructure unified under Redis.

**Time to first value is days, not weeks.** The team can implement the core pattern — Flask emits `XADD`, worker consumes via `XREADGROUP` — in a single sprint. Kafka would require provisioning a cluster, learning the API, reworking deployment pipelines, and understanding partition/replication semantics before delivering anything.

### Operational complexity comparison

| Concern | Redis Streams | Apache Kafka |
|---|---|---|
| New infrastructure to run | None (already running) | Full cluster (brokers, ZK/KRaft) |
| Team learning curve | Days (Redis API familiar) | Weeks (new tool, new concepts) |
| Monitoring | Extend existing Redis dashboards | New dashboards, new alert rules |
| Backup / restore | Standard Redis RDB/AOF | Kafka-specific tooling |
| Scaling beyond 1 node | Possible with Redis Cluster | Built-in via partitioning |

---

## Consequences

### Pros

- **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. No new AWS resources, no new Terraform modules, no new security group audits.
- **Rapid delivery.** The `XADD` / `XREADGROUP` / `XACK` pattern can be production-ready in one sprint. Kafka would take 2–4 sprints before the team is comfortable with the operational model.
- **Low operational burden.** A 6-person team with no dedicated infra engineer can own Redis Streams — it is a single process they already manage. Kafka's broker cluster, partition rebalancing, and log compaction are significantly harder to operate without dedicated tooling.
- **Natural fit for current scale.** At 500 req/s peak (5,000 under 10× growth), Redis Streams is over-provisioned. Kafka's strengths (infinite retention, multi-datacenter replication, massive fan-out) are irrelevant at this load.
- **Unified data plane.** Because the same Redis instance handles session storage, rate limiting, and the notification stream, there is one attack surface, one credential rotation, one monitoring dashboard.
- **Good enough ordering.** Events are stored in the order they arrive; consumers within a group receive them in that order. True global ordering across partitions would require Kafka, but the notification use case does not need it — each task update is independent.

### Cons

- **Memory-bound retention.** Redis Streams lives in RAM (RDB/AOF persistence writes to disk, but the working set is in memory). At 5,000 events/s with ~2 KB payloads, a 24-hour window consumes ~860 MB — manageable today but requires monitoring as the event volume or payload size grows. Kafka stores to disk natively and can retain data indefinitely with less memory pressure.
- **No built-in exactly-once.** Redis Streams provides at-least-once; exactly-once requires idempotency keys in the application layer. This is a well-known pattern, but it means the billing consumer must carry extra logic.
- **Single-node bottleneck risk.** A single Redis node (or single primary in a Cluster setup) is a throughput cap. If traffic far exceeds 10× growth (say 100×), Kafka's partitioning model would be easier to scale. At that point the team can reassess — the ADR is not a permanent contract.
- **No native replay by timestamp.** Kafka allows replaying from any offset or timestamp. Redis Streams requires range queries by ID. Both can do it; Kafka's ergonomics are slightly better here, but the team has no Kafka experience to benefit from that.

---

## Alternatives Considered

### Apache Kafka (rejected)

Kafka is the gold standard for high-throughput event streaming with strong durability guarantees. It offers:

- **Persistent storage on disk** — events can be retained for months regardless of memory.
- **Exactly-once semantics** — via the transactional producer and consumer APIs.
- **Horizontal partitioning** — a topic's partitions can be spread across many brokers, scaling to hundreds of thousands of events per second.
- **Built-in replay** — consumers can rewind to any offset or timestamp.

**Why it was rejected for this context:**

1. **No team experience.** Three weeks of learning and experimentation before the first event flows through Kafka. The constraint is two weeks to value. Kafka cannot meet that timeline.
2. **Operational overhead for a 6-person team.** A Kafka cluster needs at least 3 broker nodes (production recommendation), ZooKeeper or KRaft quorum, EBS volumes with tuned IOPs, monitoring for ISR shrinks, partition leadership changes, and consumer lag. Without a dedicated infra engineer, this is a chronic maintenance tax.
3. **Over-engineered for the load.** Kafka is designed for the 100k msg/s use case. The current system pushes 500 req/s. Even at 10× growth, Redis Streams handles it comfortably. Paying the Kafka complexity tax for headroom that may never be used is a poor trade-off.
4. **Cost.** Managed Kafka on AWS (MSK) starts at ~$0.50/hr for a 3-broker cluster (~$360/month) before storage and data transfer. Self-hosted Kafka requires several EC2 instances (3–5 brokers) plus EBS volumes. Redis Streams on an existing ElastiCache node costs exactly $0 in additional spend. The budget constraint explicitly rules out Confluent Cloud.
5. **Integration friction.** The team would need to adopt a new client library (`confluent-kafka-python` or `kafka-python`), learn its configuration surface, and build new deployment/health-check tooling. Redis Streams uses `redis-py` — the same library already in the project for session storage.

**Conclusion:** Kafka is the correct answer for a different organization — one with a dedicated infrastructure team, existing Kafka expertise, or a requirement for 100k+ events/s with unlimited retention. None of those conditions hold here.

### Celery / RabbitMQ (briefly considered, rejected)

A traditional task queue (Celery + RabbitMQ or Celery + Redis) would also decouple the request cycle from notification delivery. It was rejected because:

- Celery's broker model does not provide persistent stream semantics — consumed messages are deleted, making replay and dead-letter patterns more awkward.
- Consumer groups in Streams map directly to independent worker pools (email workers, webhook workers, future WebSocket workers). Celery's routing is queue-based and must be wired up separately.
- Stream-based processing is a stronger foundation for the WebSocket push requirement planned for Q2.

---

*Approved by: [pending]*  
*Date: 2026-07-06*
