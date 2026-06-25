# ADR-001: Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-06-25

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails and webhooks on task updates, assignments, and completions — synchronously inside the HTTP request cycle. This has caused four production incidents:

1. **Request timeouts** — Average latency 800ms, spikes to 8s during peak hours.
2. **Silent failures** — No retry or dead-letter queue when an email provider or webhook endpoint is down.
3. **Cascading failures** — Two incidents this year where a slow webhook endpoint exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees** — Billing-critical notifications ("trial expired", "payment failed") have no exactly-once guarantee.

We need to decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), prepare for real-time WebSocket push notifications within 2 quarters, and handle 10x traffic growth without re-architecting.

Our constraints are significant:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Timeline**: Must deliver value within 2 weeks of starting.
- **Budget**: Modest — managed Confluent Cloud at full scale is not affordable today.
- **Existing stack**: Redis already in production for session storage and rate limiting. Zero Kafka experience on the team.

## Decision

We will use **Redis Streams** as the message broker for the notification subsystem.

The deciding factors are:

1. **Operational readiness.** We already run Redis in production. The team has operational runbooks, monitoring, and on-call experience with it. Adding Streams to the existing Redis deployment requires configuration changes, not a new distributed system.

2. **Time to value.** A Redis Streams consumer can be operational in days — the Python `redis` library supports `XADD`, `XREADGROUP`, `XACK`, and `XPENDING` natively. Kafka would require cluster provisioning, security configuration, topic design, and operator training before the first message flows.

3. **Sufficient throughput.** Redis Streams handles hundreds of thousands of messages per second on a single instance. Our current peak is ~500 req/s; even at 10x with 5 notifications per action, we reach ~25K msg/s — well within Redis Streams' capability.

4. **Consumer groups.** Redis Streams provides native consumer groups (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`) that support the retry, redelivery, and dead-letter semantics we need. Each notification type (email, webhook, push) becomes a separate stream with its own consumer group, enabling independent scaling and failure isolation.

5. **Exactly-once for billing.** Redis Streams provides at-least-once delivery by default. We achieve exactly-once semantics for billing notifications through application-level idempotency: each billing event carries a unique `notification_id`, and the consumer records the processed ID in PostgreSQL before performing the side effect. On redelivery, the consumer checks the idempotency table and skips already-processed events. This is a well-understood pattern that trades a small PostgreSQL write for a strong guarantee — appropriate given that our PostgreSQL instance is already the system of record.

## Consequences

### Pros

- **Fast delivery.** We can ship a working async notification pipeline within the 2-week constraint. No new infrastructure to provision, secure, or learn.
- **No additional operational burden.** Redis is already in our runbooks, dashboards, and on-call rotation. We extend an existing system rather than introducing a new one.
- **Consumer group semantics.** Built-in support for grouped consumption, pending-entry lists for retry, and claim mechanics for dead-letter routing — the primitives we need for reliable delivery.
- **Per-stream ordering.** Messages within a single Redis Stream are strictly ordered by insertion time (ID-based). This ensures that notifications for a given entity (e.g., a task) are processed in the order they were produced.
- **Cost-neutral.** No new infrastructure spend. Our existing Redis instance has headroom for the projected message volume.
- **WebSocket readiness.** Redis Pub/Sub (already available) complements Streams for real-time fan-out to WebSocket servers, allowing us to add push notifications without introducing another broker.
- **Simple failure model.** A single Redis instance failure is easier to reason about and recover from than a multi-broker Kafka partition rebalance. With AOF persistence enabled, we lose at most 1 second of data on crash.

### Cons

- **No native exactly-once.** We must implement idempotency in the application layer using PostgreSQL. This is correct and standard, but it adds code and a database round-trip per billing notification. If we later need exactly-once across more event types, each consumer must implement the same pattern.
- **Retention is finite.** Redis Streams uses `MAXLEN` trimming or time-based expiry. Old messages are eventually deleted. For audit and replay beyond the active processing window, we must archive to PostgreSQL or object storage. Kafka's configurable long-term retention is simpler for this use case.
- **Single-node availability.** Our current Redis is a single instance. A failover requires Redis Sentinel or Cluster, which adds complexity. Kafka's replication is built-in. However, for our volume and team size, Redis Sentinel with automatic failover is far simpler to operate than a Kafka cluster.
- **No built-in schema registry.** Kafka has Confluent Schema Registry for enforcing message contracts. With Redis Streams, we enforce schemas in application code and tests. At our scale, this is manageable; at significantly larger scale, it becomes a liability.
- **Scaling ceiling.** Redis Streams tops out at a single node's memory and network bandwidth. If we exceed ~500K msg/s or need multi-terabyte retention, we will need to migrate to Kafka or a similar system. This ADR accepts that ceiling as acceptable given our 10x growth target (~25K msg/s).

## Alternatives Considered

### Apache Kafka

Kafka is the stronger technology in isolation: partition-level ordering, configurable long-term retention, native consumer groups with cooperative rebalancing, transactional exactly-once semantics via idempotent producers and transactional consumers, and horizontal scalability to millions of messages per second across a cluster.

We reject Kafka for this decision based on our constraints:

- **Zero team experience.** No one on the team has operated Kafka. The learning curve — topic design, partition strategy, consumer group management, rebalancing behavior, monitoring — would consume the 2-week window before delivering any business value.
- **Operational overhead.** Kafka requires brokers, controllers (or ZooKeeper for older versions), and ongoing capacity planning. We have no dedicated infrastructure engineer. A misconfigured Kafka cluster is worse than no cluster — it introduces new failure modes (partition leader elections, replica lag, under-replicated partitions) that our team cannot yet diagnose.
- **Cost.** Managed Kafka (Confluent Cloud, AWS MSK) starts at ~$0.15/GB ingested plus per-partition fees. At our projected volume, this is a meaningful ongoing cost our budget cannot absorb. Self-managed Kafka on EC2 requires 3+ broker nodes plus monitoring — also outside budget.
- **Setup time.** Provisioning, securing, and validating a Kafka cluster — even managed — takes longer than configuring consumer groups on an existing Redis instance.

Kafka may become the right choice in the future if our volume exceeds Redis Streams' comfortable capacity or we need long-term event replay as a core capability. At that point, we will have the team experience from operating Redis Streams and a clear migration path: consumers read from both Redis Streams and Kafka during transition, with PostgreSQL as the idempotency anchor throughout.

### Other alternatives considered and rejected

- **RabbitMQ**: Provides reliable delivery and dead-letter exchanges, but adds a new operational dependency with no team experience. Does not offer a meaningful advantage over Redis Streams for our use case, and its throughput ceiling is comparable.
- **SQS/SNS**: Fully managed and operationally simple, but introduces AWS lock-in, higher latency per message, and no native consumer-group equivalent (requires SNS fan-out to multiple SQS queues). The latency overhead is problematic for our WebSocket push requirement.
- **Database-backed queue (PostgreSQL SKIP LOCKED)**: Simplest option, but polling-based consumption increases database load under our PostgreSQL is already the system of record. Does not support the fan-out pattern we need for WebSocket push without additional polling complexity.