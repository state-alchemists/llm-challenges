# ADR-001: Notification Subsystem — Async Messaging Architecture

**Status:** Proposed

---

## Context

The notifications module (emails + webhooks for task updates, assignments, completions) runs synchronously inside the Flask HTTP request cycle. At 500 req/s peak with 85k MAU, this causes:

- **Request timeouts** — notification delivery adds 800ms average latency, spiking to 8s.
- **Silent failures** — downstream email/webhook failures drop the notification with no retry or dead-letter queue.
- **Cascading failures** — two incidents where a slow webhook endpoint exhausted the PostgreSQL connection pool, taking down unrelated features.
- **No delivery guarantees** — billing-critical notifications (trial expired, payment failed) need at-least-once delivery with exactly-once semantics where feasible, but today get none.

### Constraints

| Constraint | Weight |
|---|---|
| 6-person team, no dedicated infra engineer, no Kafka experience | Hard |
| Redis already running in production (session, rate limiting) | Fact |
| Must deliver value within 2 weeks of starting work | Hard |
| Budget modest — no managed Confluent Cloud | Hard |
| Must handle 10x traffic growth without re-architecting | Hard |
| Exactly-once semantics for billing notifications | Hard |

---

## Decision

**Use Redis Streams** as the notification message bus, backed by the existing Redis instance. Pair it with a lightweight Python consumer daemon (`redis-py` + consumer groups) that processes notifications asynchronously with retry, backoff, and a dead-letter queue.

### Architecture (brief)

```
HTTP Request → Flask handler → XADD to Redis Stream
                                   ↓
                     Worker (XREADGROUP, consumer group)
                                   ↓
                    ┌──────────────┼──────────────┐
                    ↓              ↓              ↓
              Email provider   Webhook #1    Webhook #2
                    ↓              ↓              ↓
               ACK to stream  ACK to stream  ACK to stream
                    ↓              ↓              ↓
              On failure → retry (exponential backoff, max 5)
                    ↓         ↓
              Dead-letter stream (manual review)

Future: WebSocket push ← Redis Pub/Sub ← same worker emits to both
```

---

## Consequences

### Pros

1. **Zero new infrastructure.** Redis is already deployed, configured, monitored, and backed up. We add a stream and a consumer group — nothing new to provision or patch.

2. **Fast time-to-value.** A senior engineer can have a working producer + consumer in a day. Within one week we can cut over email notifications. The 2-week deadline is comfortable, not tight.

3. **Fits the scale.** A single Redis instance handles 100k+ ops/second. At 500 req/s today (~1-2 notifications/req ≈ 1k msg/s), we use ~1% of capacity. At 10x (5k req/s, ~10k msg/s), we're still under 10%. No partitioning or cluster mode needed.

4. **Consumer groups.** `XREADGROUP` gives us exactly the same consumer-group semantics as Kafka — work is distributed among N workers, each message is delivered to one consumer. Group rebalancing on consumer join/leave is automatic at this scale, with no manual partition assignment.

5. **Ordering guarantees.** Within a single stream, messages are strictly ordered by arrival. For per-task ordering (e.g., "don't send 'completed' before 'started'"), we partition by task via separate streams or a consumer-group design where one consumer handles one task's event sequence. Same approach as Kafka partitions, with less ceremony.

6. **Retry and dead-letter are built into the consumer, not the broker.** This is an advantage: retry logic lives in application code where it's testable, debuggable, and deployable without broker restarts. Our workers use configurable exponential backoff (1s, 2s, 4s, 8s, 16s → DLQ) with `XPENDING` to track pending deliveries.

7. **Exactly-once for billing is achievable via consumer-side idempotency.** True end-to-end exactly-once is impossible for webhook delivery regardless of broker choice — the webhook receiver can process a request successfully but fail to return 200. The standard pattern is: at-least-once delivery + idempotency key on the consumer. Redis Streams supports this pattern identically to Kafka. We add an `Idempotency-Key` header to billing webhooks and deduplicate on the receiver side against a Redis SET (TTL 24h). This is the same approach used with Kafka.

8. **WebSocket push (Q2 roadmap) integrates naturally.** Redis Pub/Sub fires WebSocket events from the same worker that ACKs the notification stream. No second message bus, no cross-system bridging. The Kafka path would require either Kafka → WebSocket gateway code or a second stack (e.g., Kafka Connect → Redis → WebSocket), adding complexity.

9. **Operational simplicity for a 6-person team.** No ZooKeeper/KRaft cluster. No partition rebalancing incidents. No broker disk sizing for log retention. The ops burden is: monitor Redis memory, set `maxlen` on streams (~100k entries, auto-trim), ensure AOF persistence is on. That's it.

### Cons

1. **Memory-bound retention.** Kafka retains messages on disk by size/time regardless of RAM. Redis Streams with `maxlen` trim oldest entries. For our use case (notifications acknowledged within seconds, DLQ inspected within hours), `maxlen=100000` per stream keeps memory under 100MB and no message lives beyond a day. If a consumer is down longer than that, old messages are lost. Mitigation: monitor `XPENDING` age in the DLQ stream; alert if messages sit pending >1 hour. If archival becomes necessary later, stream messages into S3 via a secondary consumer.

2. **No native exactly-once** (within the broker). Kafka's transaction API provides exactly-once semantics from producer to consumer within the Kafka cluster. Redis Streams does not. However, as argued in the pros, end-to-end exactly-once for webhook delivery always requires consumer-side idempotency — Kafka's broker-level exactly-once handles only the transport leg, which is the least failure-prone leg. The cost of implementing the same idempotency on Redis Streams is negligible (one header, one SET with TTL).

3. **Consumer group rebalancing is less sophisticated.** Kafka uses a configurable partition-assignment strategy (range, round-robin, sticky, cooperative sticky). Redis uses simple round-robin within `XREADGROUP`. At our scale (fewer than 10 consumers), this difference is irrelevant. At very large scale (>50 consumers per stream), Redis consumer group performance degrades. At 10x growth we'll have ~6-8 consumers, well within comfort.

4. **Redis is single-threaded for commands.** Long-running commands (e.g., `XRANGE` on a huge stream) can block other operations. Mitigation: our stream operations are `XADD` (O(1)), `XREADGROUP` (O(log N)), and `XACK` (O(1)). No long scans. Rate-limiting sessions use cheap operations. At our projected load, Redis handles 1k msg/s + session lookups on a single `cache2.micro` node without strain.

5. **No Kafka ecosystem.** Kafka Connect, Kafka Streams, Schema Registry — none of these apply. We don't need them. Notifications are a 2-hour-latency-tolerant workload with no complex streaming jobs.

---

## Alternatives Considered

### Apache Kafka (Rejected)

**Why it was considered:** Kafka is the industry standard for async event streaming. Its log-based persistence, configurable retention, partition-based ordering, and consumer-group rebalancing make it the default choice for serious async workloads.

**Why it was rejected — four disqualifying factors:**

1. **Operational cost exceeds the budget and team capacity.** Self-hosted Kafka requires a minimum of 3 ZooKeeper nodes + 3 broker nodes — 6 EC2 instances, EBS volumes sized for retention, network throughput planning, JMX monitoring, partition rebalancing during scaling events, and KRaft migration in the near term. For a 6-person team with no dedicated infra engineer, this is not sustainable. Managed Kafka (MSK) starts at ~$200/month for a minimal cluster but doubles the per-node cost with Confluent Cloud explicitly ruled out.

2. **2-week delivery deadline is incompatible.** The team has zero Kafka experience. Learning producers/consumers, tuning broker configs, setting up monitoring alerting for ISR shrinks, leader election, and consumer lag — then CI-testing it — takes 4-6 weeks minimum for a team at this experience level. Redis Streams delivers in under a week.

3. **Over-engineered for the workload.** At 500 req/s (1k msg/s today, 10k msg/s at 10x growth), Kafka is enormous overcapability. It is designed for 100k msg/s+ at the low end. Running Kafka at this throughput means paying for all the operational complexity for 1-10% of Kafka's design capacity. Redis Streams matches the throughput requirement with no excess operational surface.

4. **WebSocket integration adds another stack.** Roadmap WebSocket push would require either a Kafka → WebSocket bridge (custom code) or a Kafka → Redis → WebSocket pipeline (adding Redis back into the stack anyway). Redis Streams avoids this indirection entirely.

**When would Kafka make sense?** If our traffic were 100k req/s+, or if we needed long-term event retention (weeks+), or if the team had Kafka experience already, or if the notification workload included complex stream processing (joins, aggregations, windowing). None of these are true today or projected within 2 years.

### PostgreSQL NOTIFY/LISTEN (Rejected)

Briefly considered because we already run PostgreSQL. Rejected because: message size limited to 8kB, no consumer groups (every listener gets every message — can't distribute work), no persistence (missed messages are lost if the listener is disconnected), and no acknowledgment semantics. These are hard constraints for billing notifications.

### SQS + SNS (Rejected)

Natural fit for scale and cost-per-message. Rejected because: adds AWS vendor lock-in for the message bus, requires IAM credential management across services, no ordering guarantees in standard queues (FIFO queues cap throughput at 300 TPS — insufficient at 10x growth), no native retry with backoff that's visible to the application (visibility timeout works but is opaque), and WebSocket push would still need a separate path. If the team had stronger AWS experience this could be viable, but given equal unfamiliarity and the advantage of zero-new-infrastructure with Redis, SQS falls behind.

---

## Recommendation

**Adopt Redis Streams.** Move the notification producer to `XADD` a Redis stream during the HTTP request (non-blocking, <1ms), and build a consumer daemon with `XREADGROUP` to process, retry, and dead-letter. Deliver value in one week. Plan the WebSocket push path as a Pub/Sub feed from the same daemon.

The decision is unanimous on the four hard constraints: it's the only option that satisfies the 2-week timeline, the 6-person team's operational capacity, the budget, and the exactly-once-for-billing requirement without introducing a new infrastructure category.
