# ADR-001: Notification Subsystem — Async Processing Architecture

**Status:** Proposed

---

## Context

The Notifier subsystem sends emails and webhooks when tasks are created, updated, assigned, or completed on our SaaS project management platform (85k MAU, ~2M tasks/month, ~500 req/s peak). Notifications are currently handled synchronously inside the Flask HTTP request cycle, causing three classes of production incident:

1. **Request timeouts** — average response latency of 800ms, spiking to 8s, because outbound email and webhook calls block the response.
2. **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry, no dead-letter queue, and no observability.
3. **Cascading failures** — two incidents this year where a slow webhook exhausted the PostgreSQL connection pool, taking down unrelated API endpoints.

We have four technical requirements and five hard constraints driving this decision.

**Requirements:**

- Decouple notification delivery from the HTTP request cycle.
- Support retry with exponential backoff and a dead-letter queue.
- Provide at-least-once delivery for all notifications; exactly-once delivery for billing-critical events ("trial expired", "payment failed").
- Support a future WebSocket push notification layer (target: within 2 quarters) without a second infrastructure build-out.

**Constraints:**

- Engineering team of six (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already runs in production for session storage and rate limiting.
- Zero in-house Kafka experience; no capacity for a multi-week learning curve.
- Setup and migration must deliver value within 2 weeks.
- Budget is modest — managed Kafka (Confluent Cloud) is out of reach at full scale.
- Exactly-once semantics are a firm requirement for billing notifications.

---

## Decision

**Adopt Redis Streams as the notification queue and async delivery substrate.**

We will use Redis Streams with consumer groups for fan-out processing, a combination of `XPENDING`-based retry logic and idempotency keys for exactly-once billing delivery, and Redis Pub/Sub as the bridge to the future WebSocket push layer.

Redis Streams satisfies every requirement within the given constraints. Kafka offers superior long-term scalability and richer built-in guarantees, but it fails three of the five constraints — team readiness, setup timeline, and budget — which Redis Streams satisfies trivially.

---

## Consequences

### ✅ Advantages

- **Zero new infrastructure.** Redis is already deployed, monitored, and understood by the team. No new ZooKeeper or KRaft clusters, no new EC2 instances, no new IAM policies. The incremental operational cost is zero.
- **Rapid delivery.** A working prototype (push notification to stream, consumer that retries with backoff, basic dead-letter queue) can ship within days and be production-hardened inside the 2-week window.
- **Adequate throughput.** At 500 req/s peak today, and even at 10× (5,000 req/s), Redis handles this comfortably — a single modest Redis instance manages 100k+ operations/second. Throughput is not the constraint.
- **Natural WebSocket path.** Redis Pub/Sub (already available in the same Redis process) is a mature, well-documented pattern for fanning stream messages to WebSocket connections. No additional broker needed.
- **Consumer groups work.** `XREADGROUP` with `XACK` provides at-least-once delivery out of the box. `XPENDING` + `XCLAIM` handles consumer failure and retry. This is a solved pattern with battle-tested libraries (`redis-py`).
- **Within-team expertise.** Every engineer on the team has written Redis code. The learning surface for Redis Streams is small — the entire API is ~10 commands.
- **Budget-friendly.** $0 incremental infrastructure cost.

### ❌ Disadvantages

- **No native exactly-once delivery.** Redis Streams gives at-least-once. To achieve exactly-once for billing notifications, we must implement consumer-side idempotency (see *Mitigations* below). This adds ~3–5 days of engineering work and a small per-message overhead.
- **Memory-bound retention.** Stream entries are stored in RAM. Long retention windows (days/weeks) consume expensive memory. Mitigation: trim aggressively with `XADD MAXLEN ~ 10000` and use PostgreSQL for long-term audit trails. Notification replay from secondary storage is a separate concern.
- **No automatic consumer rebalancing.** If a consumer crashes, `XCLAIM` requires manual or scheduled rebalancing. Mitigation: for a single consumer group with 2–3 consumers, the pattern is simple and well understood; we run a small monitoring loop (`XPENDING` + `XCLAIM` on a timer) rather than a full rebalance protocol.
- **No built-in dead-letter queue.** Must be implemented as a separate stream that entries are moved to after N failed delivery attempts. This is ~50 lines of Python.
- **Scaling ceiling is lower than Kafka.** A single Redis stream is limited to one Redis instance's RAM and the single-threaded event loop. For workloads beyond ~50k messages/second with large payloads, Kafka would win. Our projected peak (5k–10k req/s after 10× growth) is well below this threshold.

### Mitigations

#### Exactly-once for billing notifications

Each billing notification carries an idempotency key derived from the event payload (e.g., `SHA256(notification_type + task_id + user_id + event_timestamp)`). The consumer:

1. Atomically checks-and-sets the idempotency key in a Redis SET with a TTL of 7 days.
2. If the key already exists, `XACK` the stream entry and skip processing.
3. If the key is new, process the notification, then `XACK`.

This gives effective exactly-once semantics. The same pattern is recommended in Kafka deployments too — Kafka's exactly-once guarantees apply to the producer-broker hop, not end-to-end.

#### Memory pressure

```
XADD notifications MAXLEN ~ 50000 * ...
```

The `~` (tilde) allows Redis to trim lazily, keeping memory predictable. Notifications that need longer retention (e.g., audit) are archived to PostgreSQL by the consumer after successful delivery.

---

## Alternatives Considered

### Apache Kafka

Kafka was the primary alternative. It offers several genuine advantages:

- **Native exactly-once semantics** via idempotent producers and transactions, reducing manual idempotency work.
- **Disk-based retention** with configurable compaction and replay from any offset.
- **Partition-level ordering guarantees** without the single-threaded ceiling of Redis.
- **Mature consumer group protocol** with automatic rebalancing, offset commits, and built-in dead-letter queue support.
- **Higher absolute throughput** (millions of messages/second).

**Why it was rejected:**

1. **Team readiness.** No one on a 6-person team has Kafka production experience. The learning curve (topic design, partitioning strategies, consumer group rebalancing, log compaction, ZooKeeper/KRaft administration, monitoring with Burrow or Cruise Control) would consume our only senior engineers for weeks — during which the notification subsystem remains broken. This violates the 2-week delivery constraint.

2. **Infrastructure burden.** A production Kafka deployment requires a minimum of 3 brokers (multi-AZ for resilience) plus a ZooKeeper or KRaft quorum. That's 3–6 new EC2 instances to patch, monitor, backup, and tune. On a team with no dedicated infrastructure engineer, this is a meaningful operational tax every week.

3. **Budget.** Managed Kafka (Confluent Cloud) would eliminate the ops burden but is explicitly out of budget at our scale. Self-hosted Kafka requires the EC2 costs plus engineering time that our current team cannot spare.

4. **Overkill for the workload.** Kafka excels at 100k–1M messages/second across dozens of partitions with hours-to-days of retention. Our workload is 500 req/s today, 5k req/s at 10× growth. Redis Streams handles this throughput trivially. Introducing Kafka at this scale is paying complexity for capacity we will not use for 2–3 years, if ever.

5. **WebSocket push still needs a bridge.** Kafka does not natively speak WebSocket. We would still need to build or buy a bridge (Kafka Connect + a WebSocket sink connector, or a custom consumer). Redis Pub/Sub under Redis Streams is a simpler, single-process solution.

### Other (not deeply evaluated)

- **RabbitMQ** — Strong option with mature retry/DLX and a smaller operational footprint than Kafka. Rejected mainly because we do not run RabbitMQ today and the Redis-Streams path requires zero new infrastructure. The team would also need to learn Erlang-adjacent tooling for deep debugging.
- **PostgreSQL as a queue (SKIP LOCKED)** — Simple and perfectly crash-safe but cannot support the WebSocket push requirement without an additional broker layer, and polling patterns do not meet the latency targets for real-time notifications.

---

## Recommendation

**Use Redis Streams.** Ship the async notification subsystem within 2 weeks, add idempotency keys for billing events, and defer the Kafka conversation until the team grows, the traffic exceeds 50k req/s, or the budget for managed infrastructure materializes. By then, the learnings from this implementation (partitioning strategy, consumer patterns, error handling) will transfer directly to a future Kafka migration — the streaming concepts are the same; only the operational complexity differs.

---

*Authored by Engineering team, June 2026.*
