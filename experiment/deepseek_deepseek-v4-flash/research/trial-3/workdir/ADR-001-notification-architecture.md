# ADR-001: Notification Subsystem — Async Messaging Backbone

**Status:** Proposed

---

## Context

The notification module (emails and webhooks for task create/update/assign/complete events) runs synchronously inside the Flask HTTP request cycle. As the platform has grown to 85K MAU, ~2M tasks/month, and 500 req/s peak, this design has produced four concrete failures:

1. **Request timeouts** — notifications add 800ms average latency (8s spikes), degrading every endpoint that triggers them.
2. **Silent failures** — email provider or webhook endpoint downtime drops the notification with no retry, no dead-letter queue.
3. **Cascading failures** — slow webhook endpoints exhausted the PostgreSQL connection pool twice this year, taking down billing and task CRUD endpoints.
4. **No delivery guarantees** — billing-critical events ("trial expired", "payment failed") must be delivered exactly once but have zero reliability today.

### Requirements

- Async decoupling: producers publish to a queue; workers consume and dispatch.
- At-least-once delivery for all notifications; exactly-once for billing events.
- Retry with exponential backoff and a dead-letter queue for persistent failures.
- Real-time WebSocket push within two quarters (streamed from the same backbone).
- Headroom for 10× traffic growth (5,000 req/s peak, ~15K notification events/s).
- Deployable within two weeks with a team of six (no dedicated infrastructure engineer).

### Constraints

| Constraint | Detail |
|---|---|
| Team | 6 engineers (3 senior, 3 mid-level), no infra specialist |
| Existing infrastructure | Redis already in production (session storage, rate limiting) |
| Kafka experience | Zero on the team |
| Budget | Modest — managed Confluent Cloud is out of scope at full scale |
| Timeline | First value delivered within 2 weeks of starting |

---

## Decision

**Use Redis Streams** as the async messaging backbone for notifications.

Redis Streams provides consumer groups, at-least-once delivery via acknowledgment (XACK), pending-entry inspection (XPENDING), and retry mechanics (XCLAIM) — sufficient to meet every requirement — while adding zero new infrastructure to a team that already runs Redis in production.

### Implementation Approach

```
┌──────────────┐    XADD     ┌──────────────────┐
│  Flask App   │──────────►  │  Redis Streams   │
│  (Producer)  │             │  notif:events     │
└──────────────┘             └────────┬─────────┘
                                      │ XREADGROUP
                                      ▼
                              ┌──────────────────┐
                              │  Worker Pool     │
                              │  (3-5 consumers) │
                              ├──────────────────┤
                              │ At-least-once    │
                              │ + idempotency    │
                              │ keys for billing │
                              └────┬────────┬────┘
                                   │        │
                                   ▼        ▼
                           ┌──────────┐ ┌────────┐
                           │ SendGrid │ │Webhook │
                           │ (email)  │ │  HTTP  │
                           └──────────┘ └────────┘
```

**Key mechanics:**

1. **Producer** — Flask routes call `XADD notif:events MAXLEN ~ 100_000 * ...` after committing the DB transaction.
2. **Consumer groups** — each worker type (email, webhook, future WebSocket) reads via `XREADGROUP` from its own group on the same stream.
3. **Retry** — workers `XACK` on success. A supervisor cron (or lightweight background thread) runs `XPENDING` periodically and `XCLAIM`s entries older than the backoff window to a retry consumer.
4. **Dead-letter** — entries exceeding max retries (`N=5`) are moved to `notif:dead-letter` via `XADD` and removed from the main stream.
5. **Exactly-once for billing** — at-least-once delivery from Redis + idempotency keys (a `billing_event_id` upserted with a unique constraint in PostgreSQL). The consumer checks the idempotency key before dispatching; duplicate delivery is detected and silently dropped.
6. **WebSocket push** — a separate consumer group on the same stream feeds a WebSocket relay (e.g., `socket.io` adapter reading from Redis).

---

## Consequences

### ✅ Benefits

**Operational simplicity (decisive advantage).** The team already runs Redis. Adding streams requires no new cluster, no new daemon, no new backup procedure, no new monitoring dashboards beyond stream lag. The same `redis-py` client library already in the dependency tree works with streams. Estimated operational burden: **one afternoon** to train the team on the stream data type.

**Rapid time-to-value.** A working producer + consumer with retry can be shipping commits within **3 days**. The full system with dead-letter queue and idempotency lands well within the 2-week constraint. Kafka would require provisioning, learning, and tuning before a single message flows.

**Throughput headroom.** A single Redis instance handles ~100K–200K ops/s on AWS `cache.r6g.large`. Our 10× target is ~15K notification events/s. The margin is comfortable even without sharding. If needed, Redis Cluster scales horizontally.

**Consumer group semantics are a close fit.** `XREADGROUP` with `>` delivers only unread messages. `XPENDING` + `XCLAIM` provides exactly the retry and failure-claiming mechanism needed for a notification worker pool. No custom offset management required.

**Enables WebSocket push without a second system.** Redis Pub/Sub or an additional consumer group on the stream feeds a WebSocket relay — single backbone, two delivery channels.

**Idempotency-based exactly-once is simpler and more auditable.** Rather than Kafka's transaction API (which requires careful producer configuration, transactional coordinators, and read-committed isolation), Redis + PostgreSQL idempotency keys produce the same end result with:
- Clear failure semantics (idempotency key collision is a hard DB constraint, not a subtle protocol edge case).
- An audit trail (the `billing_event_id` and its disposition are visible in PostgreSQL).
- No transaction coordinator to monitor.

### ⚠️ Trade-offs & Risks

**Memory-bound retention.** Redis Streams live in RAM (plus optional RDB/AOF persistence). A sustained consumer lag of, say, 4 hours at 5,000 req/s (~15K events/s × 14,400 s ≈ 216M events) could consume significant memory. **Mitigation:** `MAXLEN ~ 100_000` (approximate trimming keeps the stream near 100K entries regardless of write rate). Workers must keep lag under the trim window. Alarms on stream length > 50K entries.

**No native exactly-once delivery.** Redis Streams does not provide exactly-once semantics natively. You must implement idempotent consumers, which adds application-level responsibility. For non-billing notifications (at-least-once is acceptable), the extra logic is unnecessary overhead. **Mitigation:** enforce idempotency checks only on the billing consumer group. Other groups operate with plain at-least-once.

**No built-in stream partitioning.** Kafka's partition-per-key model guarantees ordering per key and enables parallel consumption per partition. Redis Streams achieves parallelism via multiple consumer groups and sharded streams (`notif:events:shard-{0..N}`) — but this must be built by the application layer. For the near-term scale (15K events/s, single worker pool), a single stream is sufficient. Shard only when needed.

**Observability tooling is less mature.** Kafka has broad ecosystem support: Burrow for consumer lag, Kafka UI, Confluent Control Center. Redis Streams relies on `XLEN`, `XPENDING`, and custom metrics export. **Mitigation:** export stream length, consumer lag (`XPENDING` count by consumer), and dead-letter count as Prometheus metrics (one afternoon of work).

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the industry standard for high-throughput event streaming and meets every functional requirement — durable disk-based retention, partitioned ordering, exactly-once semantics (EOS), rich consumer group rebalancing, and a mature ecosystem.

**Why it was rejected for this context:**

| Factor | Assessment |
|---|---|
| **Operational cost** | Self-hosting Kafka requires dedicated infrastructure attention: KRaft/ZooKeeper health, partition leadership rebalancing, broker disk sizing, JMX metric monitoring, GC tuning on the JVM. A 6-person team with no infra specialist cannot absorb this without degrading feature velocity. |
| **Learning curve** | Zero Kafka expertise on the team. Kafka's mental model (topics vs. partitions vs. offsets vs. consumer groups vs. rebalancing protocols) takes weeks to internalize. The first production incident — say, a consumer rebalance storm or a `OffsetOutOfRangeException` — would require time-expensive debugging without senior Kafka experience on staff. |
| **Time-to-value** | Provisioning a Kafka cluster (even MSK Serverless) and wiring producers/consumers with the right acks, compression, idempotence, and transactional settings takes 2–4 weeks for a team learning Kafka. This exceeds the 2-week constraint. |
| **Budget** | MSK Serverless at 5,000 req/s (~15K events/s) costs roughly $200–400/month, which is acceptable. Managed Confluent Cloud for the same throughput is $500+/month and beyond "modest budget." Self-hosting on EC2 costs less in raw compute but far more in engineering time. |
| **Proportionality** | Kafka excels at multi-hundred-thousand-events-per-second, multi-year retention, globally ordered log compaction. Our requirement is 15K events/s with days-long retention. Kafka is the right tool for a different problem scale. |

**When to re-evaluate Kafka:** If the notification backbone evolves into a company-wide event bus (50+ event types, downstream data pipelines, long-term audit log, stream processing with Kafka Streams/ksqlDB), Kafka becomes the correct choice. This ADR should be revisited if the event scope expands beyond notifications.

### PostgreSQL LISTEN/NOTIFY (Rejected Briefly)

PostgreSQL's `LISTEN/NOTIFY` provides async notification with zero additional infrastructure — the database is already there.

**Rejected because:** notifications are not persisted; if the consumer is not connected, the notification is lost. No consumer groups, no retry mechanism, no backpressure. The payload size is limited to 8,000 bytes. Not suitable for a system requiring at-least-once delivery.

### Amazon SQS + SNS (Rejected Briefly)

SQS provides at-least-once delivery, retry with DLQ, and FIFO queues for exactly-once.

**Rejected because:** SQS has no consumer group model — each queue message is delivered to one consumer, requiring one queue per worker type (email, webhook, future WebSocket) and a fan-out mechanism (SNS) that adds complexity. SQS FIFO throttles at 300 TPS, far below our 5,000 req/s target. Cross-region data transfer costs for a multi-region future are unpredictable. The tight integration with AWS is fine for now but couples our architecture to a single cloud provider for a relatively generic messaging need.

---

## Recommendation

Start with **Redis Streams**. The decision is driven primarily by team constraints, not technical ceiling:

- **Week 1** — Producer writes to `notif:events` from Flask after DB commit. Single consumer group for email dispatch with XACK. Basic retry from XPENDING. This alone eliminates the request-timeout and cascading-failure problems.
- **Week 2** — Idempotency keys for billing events. Dead-letter queue. Exponential backoff. Prometheus metrics for stream length and lag.
- **Q2** — WebSocket consumer group on the same stream.

At 10× traffic, if the single stream approaches its throughput ceiling, shard by task ID (`notif:events:{task_id % N}`). At 50× or when non-notification event types appear, revisit Kafka.

The system goes from broken to reliable in two weeks, with no new servers, no new database, and no new vendor relationship.
