# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

### The Problem

The notification module currently executes synchronously inside the Flask HTTP request cycle. As the platform has grown to 85,000 MAU and ~2M tasks/month (peak ~500 req/s), this has caused four distinct failure modes:

1. **Request timeouts**: Notification delivery (email, webhooks) blocks the HTTP response. Average latency is 800ms; peak spikes reach 8s.
2. **Silent failures**: A downed email provider or slow webhook endpoint causes the notification to be dropped with no retry and no dead-letter queue.
3. **Cascading failures**: Two incidents this year saw a slow webhook endpoint exhaust the shared connection pool, degrading unrelated features.
4. **No delivery guarantees**: Billing-critical notifications (trial expiry, payment failure) require exactly-once delivery. The current system provides no such guarantee.

### Constraints

| Constraint | Implication |
|---|---|
| 6-person engineering team (no dedicated infra engineer) | Operational complexity must stay low. Kafka expertise is zero today. |
| No Kafka experience on the team | Kafka introduces a steep learning curve and risky operational unknowns. |
| Redis already in production (sessions, rate limiting) | Marginal cost to expand Redis usage is near zero. |
| 2-week maximum setup/migration window | Must deliver value before the team loses momentum or context. |
| Modest budget (no Confluent Cloud) | Self-managed Kafka on EC2 introduces significant ops burden. |
| Exactly-once semantics required for billing events | Non-negotiable. Failure here means revenue impact. |
| 10x traffic growth target within planning horizon | Architecture must scale without re-architecting. |

## Decision

**We choose Redis Streams.**

### Justification

Redis Streams, combined with consumer groups and application-level idempotency, satisfies all stated requirements within the team's operational constraints. Specifically:

**Throughput**: Redis Streams on a properly resourced EC2 instance handles 50,000–100,000 events/second under the Redis in-memory model. At a peak of 500 req/s generating one notification event each, the notification subsystem must sustain ~500 events/s — four orders of magnitude below Redis Streams' practical ceiling. Horizontal read replica scaling is available if needed. Kafka, for comparison, sustains higher absolute throughput (~1M+/s across a cluster), but that capacity is irrelevant when our load is 500 req/s.

**Ordering guarantees**: Redis Streams guarantees ordering per consumer group. Messages within a single stream are delivered in FIFO order to the same consumer. This is sufficient for notification ordering requirements; out-of-order delivery of duplicate notifications is handled by the idempotency layer.

**Message retention**: Redis Streams retains messages until all consumer groups have acknowledged them (via `XACK`), or until the `MAXLEN` policy evicts old entries. Unlike plain Redis pub/sub, streams are durable in the sense that unacknowledged messages survive consumer restarts.

**Consumer groups**: `XREADGROUP` provides at-least-once delivery with automatic load balancing across consumers. Failed deliveries (consumer crash, network timeout) leave the message unacknowledged; it is automatically redelivered to another consumer after the `BLOCK` timeout. This maps directly to the retry-with-backoff requirement.

**Exactly-once for billing events**: Redis Streams does not provide native exactly-once semantics. However, exactly-once delivery for billing notifications is achievable by using the billing event ID (e.g., `invoice_id` or `subscription_id`) as an idempotency key stored in Redis with a TTL. The consumer checks this key before sending; if present, it skips delivery and acknowledges the message. This is the same pattern used by Stripe and Twilio for payment webhooks. The team has Redis expertise, so this implementation carries low risk.

**Operational complexity**: This is the decisive factor. Redis is already running. The team needs no new infrastructure knowledge, no cluster provisioning, no JVM tuning (Kafka's) or ZooKeeper coordination. The operational surface area increase is minimal — add a new stream, configure consumer groups, and ship.

**Migration timeline**: A working Redis Streams producer/consumer can be implemented and deployed in days. The existing notification code path can be wrapped in a try/except that publishes to the stream and returns immediately, decoupling the hot path in under 2 weeks.

**10x growth path**: If traffic grows 10x (5,000 req/s peak), Redis Streams remains viable with vertical scaling (larger EC2 instance) and eventually read replicas for consumers. Beyond that threshold, a migration to Kafka would be warranted — but that is a good problem to have, and the Redis Streams code does not preclude a future migration.

## Consequences

### Benefits of Redis Streams

- **Fast path to value**: Decouple notification delivery from the HTTP request cycle within the 2-week constraint.
- **Zero new infrastructure**: Uses existing Redis deployment. No new servers, no cluster to manage.
- **Familiar operational model**: The team already operates Redis. Monitoring, backups, and persistence settings are already established.
- **Built-in consumer groups**: `XREADGROUP` + `XACK` provides at-least-once delivery with automatic redelivery on failure — satisfying the retry requirement with no custom code.
- **Idempotency for exactly-once**: Application-level deduplication using billing event IDs is straightforward and proven.
- **Low latency**: Redis is sub-millisecond. Notification events are picked up almost immediately after being published.

### Drawbacks of Redis Streams

- **No native exactly-once**: Requires a hand-rolled idempotency layer. Slightly more implementation work and a small window of duplicate delivery risk if a consumer crashes after sending but before `XACK`.
- **Operational ceiling**: Redis Streams is not designed for the multi-million-events/second tier. If the team expands the notification use cases significantly (e.g., adding event sourcing, audit logs, or real-time analytics pipelines), Redis Streams will become a bottleneck.
- **No native dead-letter queue**: Failed messages that exceed the retry threshold must be handled manually — moved to a separate stream (`notifications.dlq`) with alerting.
- **Single-node durability risk**: If the Redis primary fails and the team has not configured AOF or RDB persistence correctly, in-flight unacknowledged messages can be lost. This requires Redis persistence to be reviewed and hardened as part of implementation.
- **Less ecosystem tooling**: Kafka has richer integration with data pipelines (Kafka Connect, KSQL), observability (Kafka Manager, CMAK), and stream processing (Kafka Streams). Redis Streams tooling is more limited.

## Alternatives Considered

### Apache Kafka

Kafka would be the better technical choice under different constraints — specifically, a larger team, prior Kafka expertise, a managed offering (Confluent Cloud or MSK), and a longer migration runway.

**Why Kafka was rejected**:

1. **Operational complexity**: Self-managed Kafka requires ZooKeeper (or KRaft in newer versions), topic partitioning strategy, consumer group offset management, and JVM tuning. With a 6-person team and no dedicated infra engineer, this is a significant and ongoing tax.

2. **Cost and infrastructure**: Even on AWS MSK, a production Kafka cluster with replication factor 3 and proper monitoring starts at significant monthly cost. Confluent Cloud's serverless tier would fit the budget, but the team has no Kafka experience to evaluate configuration trade-offs.

3. **Learning curve**: The team has zero Kafka experience. Getting to production confidence within 2 weeks is unrealistic. The risk of misconfigured retention, incorrect consumer group offsets, or partition rebalancing causing availability incidents is high.

4. **Migration risk**: Replacing the synchronous notification path with Kafka requires a more invasive migration — a new service, Kafka client configuration, and schema registry. Redis Streams can be introduced as a side-effect of the existing code path (publish-and-return).

5. **Scale mismatch**: Kafka's strengths (durable log-based storage, multi-subscriber topics, massive throughput) are not relevant at 500 req/s. Redis Streams is the right tool for this scale.

**When Kafka would be reconsidered**: If the team grows to include a platform/infrastructure engineer, traffic exceeds ~5,000 req/s sustained, or the notification subsystem evolves into an event-sourcing backbone, Kafka's durability, multi-consumer, and ecosystem advantages become decisive.

---

## Summary

| Requirement | Redis Streams | Kafka |
|---|---|---|
| Decouple from HTTP | ✅ (publish-and-return) | ✅ |
| Retry with backoff | ✅ (consumer group redelivery) | ✅ |
| At-least-once delivery | ✅ (XREADGROUP) | ✅ |
| Exactly-once for billing | ✅ (idempotency key in Redis) | ✅ (transactions) |
| 10x growth headroom | ✅ (vertical + read replicas) | ✅ (horizontal partitioning) |
| 2-week delivery | ✅ | ❌ (too much to learn) |
| No new infrastructure | ✅ | ❌ (new cluster needed) |
| Team familiarity | ✅ (already uses Redis) | ❌ (zero experience) |
| Operational complexity | Low | High |