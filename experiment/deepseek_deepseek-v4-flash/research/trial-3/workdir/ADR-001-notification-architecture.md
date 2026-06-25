# ADR-001: Notification Subsystem — Async Event Broker

**Status:** Proposed

---

## Context

We operate a SaaS project management platform with 85,000 MAU generating ~2M tasks/month at a peak of 500 req/s. Currently, email and webhook notifications are sent synchronously within the Flask HTTP request cycle. This causes three interconnected problems:

1. **Request timeouts** — average 800ms, spikes to 8s at peak, because the response waits on external I/O (SMTP, HTTP webhook).
2. **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry, no dead-letter queue, no observability.
3. **Cascading failures** — two incidents this year where a slow webhook consumed all database connections from the pool, taking down unrelated features.

We need to decouple notification dispatch from the request cycle with an async event broker. The system must support:
- Async processing with retry and exponential backoff
- At-least-once delivery for all notifications; exactly-once for billing-critical events ("trial expired", "payment failed")
- A path to real-time WebSocket push within two quarters
- 10x traffic growth without re-architecting

**Constraints (non-negotiable):**
- 6-person engineering team, no dedicated infrastructure engineer
- Zero Kafka experience on the team; everyone knows Redis (used today for session storage and rate limiting)
- Must deliver value within 2 weeks of setup work; cannot tolerate a 1–2 month learning curve
- Modest budget — managed Confluent Cloud at full scale is unaffordable today
- Billing notifications require exactly-once semantics

---

## Decision

**Use Redis Streams as the notification event broker.**

We will introduce Redis Streams on the existing Redis instance (or a dedicated Redis node for isolation) and build lightweight worker processes that consume from consumer groups. Retry logic, dead-letter queues, and idempotent processing for billing events will be implemented at the application layer using well-documented Redis Streams primitives.

---

## Consequences

### Pros

1. **Zero new infrastructure.** Redis is already in production (session storage, rate limiting). Streams are a built-in data type — no new servers, no new state machine, no new cluster to provision. This satisfies the ≤2-week delivery constraint immediately.

2. **Familiar primitives for the team.** The existing Python/Flask codebase already uses `redis-py`. The Streams API (`XADD`, `XREADGROUP`, `XACK`, `XPENDING`, `XAUTOCLAIM`) is accessible through the same library. No JVM, no ZooKeeper/KRaft, no new wire protocol — the team can ship the first worker in days, not weeks.

3. **Consumer groups for work distribution.** Like Kafka, Redis Streams supports consumer groups: each message is delivered to exactly one consumer within a group (Redis Streams documentation, `XREADGROUP` semantics). This lets us scale notification workers horizontally by adding processes with unique consumer names.

4. **Retry and dead-letter queue are well-documented patterns.** Redis Streams provides `XPENDING` (delivery count per message), `XAUTOCLAIM` (reclaim messages from crashed consumers after an idle timeout), and the ability to `XADD` to a separate dead-letter stream. The official Redis tutorial and community patterns show a complete retry → DLQ pipeline: a worker that fails increments a delivery counter; after N retries (checked via `XPENDING`'s `times_delivered` field), the message is routed to a dead-letter stream instead of re-processed. ([Redis tutorial: Redis-backed job queue](https://redis.io/tutorials/redis-backed-job-queue-for-background-workers/))

5. **Sub-millisecond latency.** Redis Streams operates in-memory, delivering message → worker latency in the sub-millisecond range. At our current peak of 500 req/s (~1,500 notification events/s assuming ~3 notifications per task), Redis handles this on a single modest instance without breaking a sweat — documented throughput exceeds 100k ops/s.

6. **Natural fit for future WebSocket push.** The planned real-time push feature (WebSocket delivery within 2 quarters) can use Redis Pub/Sub to fan out events to WebSocket server processes, while Streams continue to handle durable email/webhook dispatch. Both are native Redis capabilities, avoiding a second infrastructure layer.

7. **AOF persistence provides crash durability.** With `appendfsync everysec`, a Redis Stream's pending entries list (PEL) survives a restart. Unacknowledged messages are visible via `XAUTOCLAIM` on recovery — no silent drops. ([Redis docs: Streams persistence](https://redis.io/docs/latest/develop/data-types/streams/))

8. **10x growth is manageable.** At 10x current load (~5,000 req/s, ~15,000 events/s), a single Redis instance with careful tuning (or a dedicated Streams Redis node with `MAXLEN ~` capping) handles the volume. If we outgrow a single node, Redis Cluster shards streams by key hash, though this adds operational complexity.

### Cons

1. **Exactly-once delivery to external systems requires application-layer idempotency.** Redis Streams does not offer native transactional consumer semantics the way Kafka does (Kafka's exactly-once relies on idempotent producers + transactional offset commits within the Kafka cluster — see [Confluent delivery semantics docs](https://docs.confluent.io/kafka/design/delivery-semantics.html)). Since our output targets are external (email provider API, webhook HTTP endpoints), **Kafka's exactly-once would not help here either** — a Kafka transaction guarantees atomicity within Kafka, not that the downstream HTTP call succeeded. Both approaches need application-level idempotency. Our plan: assign each billing notification a unique idempotency key at production time, store processed keys in PostgreSQL (`ON CONFLICT DO NOTHING`), and check before dispatching. This is the same pattern Kafka teams use for external side effects.

2. **Memory-bound retention.** Redis Streams are in-memory (even with AOF persistence, the working set lives in RAM). We must set `MAXLEN ~ <count>` to cap stream size and prevent unbounded memory growth. If long-term replay or audit trails are required, we would need to archive processed events to S3 or PostgreSQL — but this applies equally to Kafka (Kafka deletes by retention policy, and replaying terabytes of historical events for a notification queue is not a real requirement).

3. **No automatic consumer rebalancing.** If a consumer crashes, its pending messages sit in the PEL until a recovery process claims them via `XAUTOCLAIM`. Kafka handles this automatically via group coordinator rebalancing. We must implement a lightweight reclaim loop (check `XPENDING` for idle entries → `XAUTOCLAIM` → retry or DLQ). For a 6-person team this is ~50 lines of Python — manageable, but it must be built and monitored.

4. **Operational monitoring must be added.** Redis provides `XINFO GROUPS`, `XINFO CONSUMERS`, and `XLEN` for stream observability. We need to instrument these (stream depth, consumer lag, pending count) and feed them into our existing metrics pipeline. Kafka ships with built-in metrics via JMX and community integrations — but this benefit is moot when we don't run Kafka.

5. **Partitioning is fixed at stream creation.** Unlike Kafka, where partition count can be increased and data rebalanced, a Redis Stream is a single logical append-only log. To parallelize beyond what a single consumer group on one stream provides, you shard by routing different notification types to different stream keys (e.g., `notifications:email`, `notifications:webhook`). This is a simple naming convention and works well for our domain.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the industry-standard event streaming platform and excels at the problems it was designed for: massive-scale, multi-subscriber, disk-persisted event logs with native exactly-once semantics. We rejected it for this project because:

**1. Operational complexity exceeds team capacity.**
A production Kafka deployment requires at least 3 broker nodes (for replication factor 3), ZooKeeper or KRaft for consensus, JVM heap tuning, partition rebalancing, and ongoing broker maintenance. Our team of 6 has no dedicated infrastructure engineer and no Kafka experience. The learning curve alone (topics, partitions, offsets, consumer groups, rebalancing protocols, exactly-once configuration) would push the delivery timeline past the 2-week constraint.

**2. Managed Kafka is too expensive.**
Amazon MSK starts at ~$0.20/hr per broker (3 brokers = ~$430/month in instance cost alone, plus storage). Confluent Cloud's basic tier starts at ~$0.10/GB of storage used with additional per-hour cluster fees. At our current volume (~2M messages/month, well under 1 GB/month), this is vastly overprovisioned — but the fixed costs don't shrink. For a team with a "modest budget," this is hard to justify for a notification queue.

**3. Overkill for current scale.**
Kafka is designed for millions of messages per second across multiple consumers with replay from arbitrary offsets. We need to decouple ~1,500 events/sec from the HTTP request cycle, with retry/DLQ and one primary consumer group per notification type. Redis Streams covers this entirely. The "10x growth" requirement takes us to ~15,000 events/s — still comfortably within Redis Streams territory.

**4. Exactly-once is a weaker argument than it appears.**
Kafka's exactly-once semantics operate within the cluster boundary (idempotent producer + transactional consumer, per [Confluent docs](https://docs.confluent.io/kafka/design/delivery-semantics.html)). Once the consumer makes an outbound HTTP call to an email provider, the same at-least-once gap exists — the email provider could receive the request but Kafka's offset commit could fail, or vice versa. Both approaches must solve exactly-once for external side effects the same way: idempotency keys stored in a transactional store (PostgreSQL). Kafka's native exactly-once does not eliminate this requirement for our use case.

**5. Kafka would complicate the WebSocket push path.**
The plan to add real-time WebSocket push within 2 quarters would mean either running Kafka consumers in the WebSocket server processes (tight coupling) or bridging Kafka → Redis Pub/Sub (two streaming systems). Starting with Redis Streams keeps the entire notification pipeline on one technology stack.

### RabbitMQ (Not formally evaluated)

RabbitMQ was scoped out of this ADR by requirement. It offers AMQP-based queuing with dead-letter exchanges, retry via TTL + DLX, and consumer acknowledgements. It is a strong candidate for a pure job queue workload. However, it lacks the append-only log data model needed for the planned WebSocket push fan-out (streaming to many consumers), and like Kafka, it would add a new infrastructure dependency and learning curve. Redis Streams provides both queuing and streaming in one system we already run.

---

## Summary Decision Matrix

| Criterion | Redis Streams | Apache Kafka |
|---|---|---|
| New infrastructure required | None (already running Redis) | 3+ broker cluster + KRaft |
| Team familiarity | High (existing Redis users) | Zero |
| Time to first value | <1 week | 2–4 weeks (learn + deploy) |
| Throughput at current scale (1.5k ev/s) | Trivial | Overkill |
| Throughput at 10x (15k ev/s) | Comfortable with tuning | Native |
| Message retention | Capped by memory (MAXLEN) | Disk-based, configurable |
| Exactly-once to external systems | Application idempotency required | Application idempotency required (same gap) |
| Consumer groups | Yes (manual reclaim via XAUTOCLAIM) | Yes (auto rebalance) |
| Retry + DLQ | Well-documented patterns | Native via Kafka Streams |
| WebSocket push path | Redis Pub/Sub (same stack) | Kafka → Redis bridge (two stacks) |
| Production cost | $0 incremental on existing Redis | $430+/month (MSK) or learning + toil |
| Monitoring maturity | Must instrument (XINFO, XLEN) | Rich JMX/metrics (but unused if we don't run it) |
