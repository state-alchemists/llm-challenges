# ADR-001: Notification Subsystem — Message Broker Selection

## Status

**Proposed**

## Context

The notification module currently processes emails and webhooks synchronously inside the HTTP request cycle. This has caused request timeouts averaging 800ms (spiking to 8s at peak), silent notification drops during provider outages, cascading failures from slow webhook endpoints exhausting connection pools, and no delivery guarantees for billing-critical events.

We need to decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery for billing events, and deliver exactly-once semantics where feasible — all within 2 weeks of engineering effort and without a dedicated infrastructure engineer.

**System parameters:**
- Peak throughput: ~500 req/s
- Daily notifications: ~65K–130K at current usage (~2M tasks/month)
- 10x growth target within planning horizon
- WebSocket push notifications required within 2 quarters

**Team constraints:**
- 6 engineers (3 senior, 3 mid-level), no Kafka experience, no dedicated infra engineer
- Redis already in production (session storage, rate limiting)
- Modest budget; Confluent Cloud managed Kafka is not affordable at full scale
- Hard deadline: deliver value within 2 weeks

---

## Decision

**Chosen option: Redis Streams**

Redis Streams is selected as the message broker for the notification subsystem.

**Justification:**

### 1. Operational Familiarity

The team already runs Redis in production. No new infrastructure, no new operational knowledge domain, no on-call novelties. Redis Streams is an extension of the existing Redis deployment — the same `redis-py` client, the same `redis-cli` introspection, the same monitoring stack. This directly satisfies the 2-week setup constraint.

### 2. Throughput Adequacy

At 500 req/s peak, Redis Streams comfortably handles the load. Redis single-instance can sustain 100K–200K ops/s on modest hardware. Even with 10x growth (5,000 req/s), a properly partitioned setup with consumer groups remains viable. Kafka's higher throughput ceiling (millions of events/s) is not yet warranted at our scale and would be purchased with operational complexity we cannot afford.

### 3. Ordering Guarantees

Redis Streams guarantees **per-consumer-group ordered delivery** within a stream. Messages are delivered in offset order; a consumer processes messages sequentially from its current position. For our use case — each notification is independent and idempotent — this ordering guarantee is sufficient. It is not as strong as Kafka's total partition ordering, but it covers our requirements.

### 4. Consumer Groups and Competing Consumers

Redis Streams supports **consumer groups** natively (XREADGROUP, XACK). Multiple worker processes can compete for messages, achieving horizontal scaling with automatic load balancing. This matches our 4-server deployment topology and provides the foundation for future WebSocket push workers.

### 5. Message Retention and Replay

Redis Streams retains messages until explicitly trimmed (XTRIM) or until a consumer acknowledges them. Unlike a plain Redis list, a consumer can re-read unacknowledged messages after a crash — providing at-least-once delivery out of the box.

### 6. Exactly-Once for Billing Events

Redis Streams alone provides at-least-once. To achieve exactly-once for billing notifications, we will implement **idempotent producers** using a `notifications_sent` table in PostgreSQL (keyed on a deterministic notification ID derived from event payload + timestamp). The consumer checks this table before sending and skips duplicate events. This is a well-understood pattern that works with either broker; Redis Streams requires no additional infrastructure to implement it.

### 7. Implementation Timeline

| Phase | Effort | Outcome |
|-------|--------|---------|
| Integrate `redis-py` Streams API into Flask | ~3 days | Producers enqueue notifications |
| Implement consumer group workers | ~4 days | Async notification delivery with retry |
| Add idempotency table for billing events | ~2 days | Exactly-once delivery guarantee |
| Dead-letter queue via separate stream | ~2 days | Failed message inspection and replay |
| Replace synchronous calls in Flask | ~2 days | Latency reduction, decoupling |
| **Total** | **~13 working days** | Within 2-week constraint |

Kafka setup alone — ZooKeeper/KRaft, topic configuration, partition strategy, consumer group management, schema registry, and the learning curve for 6 engineers — reliably exceeds 2 weeks before a single notification is sent.

---

## Consequences

### Pros of Redis Streams

1. **Fast implementation**: Leverages existing Redis infrastructure; team writes Python, not cluster configuration.
2. **Low operational overhead**: No new processes to monitor, no JVM tuning, no partition rebalancing procedures.
3. **Familiar tooling**: `redis-cli`, existing Redis monitoring (e.g., RedisInsight, `INFO` command), `redis-py` — all already in the team's workflow.
4. **Atomic operations**: MULTI/EXEC transactions can guard producer-side write atomicity without external coordination.
5. **Built-in consumer groups**: XREADGROUP/XACK provides competing consumers, acknowledgment, and pending entry lists out of the box.
6. **TTL and stream length**: XTRIM enforces bounded retention, preventing unbounded disk usage.
7. **WebSocket foundation**: The same Redis instance can pub/sub to push WebSocket notifications to connected clients, aligning with the 2-quarter roadmap goal.

### Cons of Redis Streams

1. **Single-node bottleneck risk**: Redis Streams on a single instance is bounded by that instance's resources. At extreme scale (100K+ req/s sustained), Redis becomes the bottleneck. Mitigation: Redis Cluster mode can shard streams across nodes, though this adds operational complexity.
2. **No native log-based retention**: Kafka's immutable log is purpose-built for replay at arbitrary offsets by any consumer group. Redis Streams is a ring buffer with acknowledgment — if all consumers acknowledge and XTRIM runs, replay is impossible. For our use case (notification delivery, not event sourcing), this is acceptable.
3. **No native exactly-once end-to-end**: Requires application-level idempotency (deduplication table). Kafka offers transactional producers for exactly-once out of the box, but at the cost of significant setup complexity.
4. **Stream awareness required**: XREADGROUP semantics differ from Kafka's poll model. Developers must understand pending entries, claim stale messages, and handleblock timeout — a learning curve, albeit a shallow one.
5. **Persistence dependency**: If the Redis instance fails and RDB/AOF recovery is slow, message delivery stalls. Running Redis with AOF `everysec` or `always` and a replicas for read operations mitigates this.
6. **Less mature monitoring ecosystem**: Kafka's metrics (consumer lag, ISR, throughput per partition) are deeper. Redis Streams metrics are available but less standardized.

---

## Alternatives Considered

### Apache Kafka

**Why it was rejected:**

1. **No Kafka experience on the team.** Kafka's operational model (brokers, ZooKeeper or KRaft, topics, partitions, consumer groups, offsets, schema registry, connect workers) requires meaningful learning investment. For a 6-person team without a dedicated infrastructure engineer, this is not a trivial cost.

2. **Setup and migration exceed 2 weeks.** Even with a managed offering (AWS MSK, Confluent Cloud), the migration path from synchronous notification calls to Kafka producers/consumers, plus testing and rollback procedures, reliably exceeds our 2-week window.

3. **Operational overhead at our scale.** Kafka is engineered for millions of events per second across many services. At 500 req/s peak with a single application's notification domain, Kafka is over-engineered. The overhead of maintaining broker health, partition leadership, replication factor, and consumer lag monitoring is disproportionate to the problem.

4. **Confluent Cloud is budget-prohibitive at full scale.** Self-managed Kafka on EC2 requires significant ops investment; managed Confluent Cloud is expensive at scale. Redis, already in the budget, has no additional infrastructure cost.

5. **Where Redis Streams falls short for Kafka advocates:** Kafka's immutable log, cross-consumer replay, and native exactly-once semantics are superior properties for event-sourcing architectures. Our notification system is not an event store — it is a job queue. Redis Streams is the right primitive for a job queue.

**When Kafka would be the correct choice:** If the platform grew to multiple teams publishing domain events, if notification volume reached 50K+ req/s sustained, if the team had a dedicated platform/infrastructure engineer, or if the system required multi-service event replay for auditing or replay testing.

---

## Summary

Given a 6-person team, no Kafka expertise, a 2-week delivery constraint, an existing Redis deployment, and a notification volume of ~500 req/s peak, **Redis Streams is the correct choice**. It delivers async notification processing, retry with exponential backoff, at-least-once delivery via acknowledgment, and application-level exactly-once for billing events — without new infrastructure, new operational knowledge, or a multi-week migration. Kafka's power is not needed at our scale and would be purchased with time and complexity we cannot afford.
