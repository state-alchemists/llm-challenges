# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

### The Problem

The notifications module (email + webhooks on task events) runs synchronously inside the HTTP request cycle. This causes:

1. **Request timeouts**: 800ms average latency, 8s spikes during peak hours due to blocking I/O.
2. **Silent failures**: Downstream email providers or webhook endpoints cause notification loss with no retry.
3. **Cascading failures**: A slow webhook endpoint caused connection pool exhaustion and took down unrelated features twice in one year.
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") lack exactly-once semantics.

### Scaling Target

- Decouple notifications from the HTTP request cycle (async processing)
- Retry with exponential backoff
- At-least-once delivery for all events; exactly-once for billing events
- WebSocket push notifications within 2 quarters
- Handle 10x traffic growth without re-architecting

### Constraints

| Constraint | Impact |
|---|---|
| 6-person engineering team (3 senior, 3 mid-level) | No dedicated infrastructure engineer; operational burden must be low |
| No Kafka experience on team | Kafka = significant learning curve + risk |
| Redis already in production (sessions, rate limiting) | Leveraging existing infra reduces complexity |
| 2-week maximum setup/migration | No multi-month infrastructure projects |
| Modest budget | Cannot afford Confluent Cloud managed Kafka at scale |
| Exactly-once required for billing notifications | Application-level idempotency needed regardless of broker |

### Observed Load

- 85,000 monthly active users
- ~2M tasks created per month
- Peak: ~500 req/s during business hours
- Target: 10x growth (~5,000 req/s peak)

---

## Decision

**Chosen Option: Redis Streams**

Redis Streams is the correct choice given the team's size, existing Redis footprint, timeline, and budget constraints.

### Justification

**1. Operational complexity matches team capacity**

The team has no dedicated infrastructure engineer. Kafka in production requires cluster provisioning, replication factor configuration, partition balancing, consumer group offset management, schema registry, and monitoring dashboards. Even with a managed service (MSK, Confluent), the operational surface area exceeds what 6 engineers with no Kafka experience can sustain alongside feature development.

Redis Streams runs on the existing Redis cluster. The team already manages Redis for sessions and rate-limiting — the operational knowledge, monitoring (Redis INFO, Redis Explorer), and on-call procedures transfer directly.

**2. Timeline is a hard constraint**

Kafka requires a minimum 2–4 weeks to set up a production-ready cluster with proper replication, security configuration, and consumer group setup. Redis Streams can be operational in 2–3 days, leaving time for idempotency logic, retry queues, and integration testing before the 2-week deadline.

**3. Throughput is sufficient for the stated scale**

| Broker | Throughput | Notes |
|---|---|---|
| Redis Streams | 100,000–300,000 events/sec | Per-node; horizontal scaling via consumer groups |
| Apache Kafka | 1,000,000+ events/sec | Requires proper partitioning and tuning |

The target is 5,000 req/s peak (10x current). Redis Streams handles this with a single consumer group on the existing Redis instance. The gap between "sufficient" and "Kafka-scale" is 2 orders of magnitude — this is not a dimension where the team should pay operational tax today.

**4. Ordering and delivery guarantees are equivalent for this use case**

Both Redis Streams and Kafka provide:
- Per-partition/per-consumer-group ordering
- At-least-once delivery with manual acknowledgment

Neither provides exactly-once semantics out of the box. Both require application-level idempotency keys for billing-critical events. This is a non-differentiator.

**5. WebSocket push notifications are achievable with Redis Streams**

Redis Streams + Redis Pub/Sub can serve real-time WebSocket delivery:
- Streams handle durable event log and retry
- Pub/Sub handles fan-out to active WebSocket connections
- The 2-quarter timeline is realistic; no Kafka migration needed

If WebSocket scale grows to millions of concurrent connections, a future migration to Kafka (which excels at fan-out to many consumers) is viable — but that is not today's problem.

---

## Consequences

### Pros of Redis Streams

1. **Fastest path to production**: 2–3 days to a working implementation vs. 2–4 weeks for Kafka.
2. **Zero new infrastructure**: Runs on the existing Redis cluster already funded and managed.
3. **Operational continuity**: The team continues using familiar Redis tooling (SENTINEL for HA, Redis Explorer, standard Redis clients).
4. **Consumer groups with ACK**: `XREADGROUP` + `XACK` provides at-least-once with per-message acknowledgment.
5. **Automatic client-side retry**: Using `XCLAIM` for dead-letter processing after `XPENDING` visibility timeout enables exponential backoff.
6. **Idempotency via Streams**: Messages can carry an idempotency key (`event_id`) in the payload; consumers deduplicate on write.
7. **Scalable to 10x**: 5,000 req/s is well within Redis Streams' capacity on existing hardware.
8. **Cost**: No additional infrastructure spend; self-managed on existing Redis.

### Cons of Redis Streams

1. **No native exactly-once**: Requires application-level deduplication using idempotency keys. This is implementable but adds code.
2. **Fan-out at scale is harder**: If WebSocket push grows to millions of concurrent connections, Redis Pub/Sub fan-out becomes a bottleneck. Kafka would handle this more elegantly.
3. **No schema registry**: Event schema evolution must be managed in application code. Kafka's schema registry is a genuine advantage for long-lived event contracts.
4. **Single-node Redis Streams throughput cap**: At very high scale (100x+ current), Redis Streams would require Redis Cluster with hash slots — more complex than single-instance Streams. Kafka handles this scale natively.
5. **Retention is shorter by default**: Redis Streams `MAXLEN` must be explicitly configured for long retention. Kafka retains for days/weeks out of the box.

---

## Alternatives Considered

### Apache Kafka

**Why rejected:**

1. **Operational complexity is prohibitive for a 6-person team with no Kafka experience.** Kafka requires careful tuning of replication factor, partition count, consumer group offsets, and producer acknowledgments. The on-call burden — diagnosing consumer lag, partition rebalancing, and broker failures — requires specialized knowledge the team does not have today.

2. **Timeline exceeds constraint.** A production-ready Kafka deployment (self-managed on EC2/ECS, or configured MSK) with proper security (SASL, encryption), monitoring (Kafka exposed metrics, Consumer Lag alerts), and disaster recovery (cross-AZ replication) requires 3–6 weeks minimum before the team can ship features on top of it.

3. **Budget mismatch.** Confluent Cloud at the scale needed for 5,000 req/s with billing-critical exactly-once requirements (requiring at least 3-broker replication, schema registry, and RBAC) costs $1,500–$4,000/month. Self-managed Kafka on EC2 requires 3+ dedicated instances ($300–$600/month) plus operational overhead.

4. **Over-engineering for current scale.** The team needs to handle 5,000 req/s peak. Kafka's strength is millions of events per second with many consumer groups. Redis Streams comfortably handles 100x the current load. Paying the Kafka operational tax for headroom the team will not need for 1–2+ years is premature optimization.

5. **WebSocket push is not a Kafka differentiator today.** Kafka's fan-out to many consumer groups is valuable at millions of connections. For a WebSocket system in the 2-quarter horizon (thousands to low tens of thousands of concurrent connections), Redis Pub/Sub + Streams is sufficient.

### Verdict

Redis Streams is the pragmatic choice. It leverages existing infrastructure, fits the 2-week constraint, matches the team's operational capacity, and provides sufficient scale for the stated 10x growth target. Kafka is the right choice if/when the system reaches 100x current scale or a dedicated infrastructure engineer joins — at that point, a migration is worth the investment.

---

## Recommendation

**Adopt Redis Streams** as the message broker for the notification subsystem. Implement the following pattern:

1. **Producers**: Flask endpoints enqueue to `NOTIFICATIONS` stream using `XADD`.
2. **Consumer group**: `XREADGROUP` with a dedicated consumer group (`notification-workers`).
3. **Retry logic**: Failed messages are `XCLAIM`ed after a visibility timeout (using `XPENDING`) with exponential backoff. After max retries, move to `NOTIFICATIONS_DLQ`.
4. **Exactly-once for billing**: Include `event_id` (UUID) in each message payload; consumers store processed IDs in a Redis Set (or PostgreSQL `notifications_processed` table) with a TTL and deduplicate before processing.
5. **Monitoring**: Expose `XPENDING` counts and consumer lag to Prometheus; alert on DLQ growth.

This delivers async notification processing, retry with backoff, and billing-grade exactly-once within the 2-week constraint.
