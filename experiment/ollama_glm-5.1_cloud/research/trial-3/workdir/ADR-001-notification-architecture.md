# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications synchronously inside the HTTP request cycle. This has caused request timeouts (800ms avg, 8s spikes), silent delivery failures with no retry, two cascading failures from slow webhooks exhausting the connection pool, and no delivery guarantees for billing-critical notifications.

We need to decouple notification delivery from request processing, add retry with exponential backoff, guarantee at-least-once delivery (and exactly-once where feasible) for billing events, and support real-time WebSocket push within 2 quarters — all while handling 10x traffic growth without re-architecting.

Constraints that shape this decision:
- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infra engineer.
- **Existing stack**: Redis already runs in production for sessions and rate limiting. No one has Kafka operations experience.
- **Time**: Must deliver value within 2 weeks of starting; no prolonged infrastructure projects.
- **Budget**: Modest — managed Confluent Cloud at scale is not affordable today.
- **Critical requirement**: Exactly-once semantics for billing notifications.

## Decision

**Use Redis Streams** as the notification subsystem's message broker, with application-level idempotency keys to achieve exactly-once delivery for billing events.

Redis Streams provides consumer groups (XREADGROUP), persistent entries with configurable retention (MAXLEN or time-based via MINID), per-message acknowledgments (XACK), and a pending entries list (XPENDING) that enables retry and dead-letter processing — all capabilities we need. We already operate Redis in production, and the team has that operational experience.

For exactly-once semantics on billing notifications, we will use a dual-write idempotency pattern: each billing event carries a UUID idempotency key, and the consumer records the key in a dedicated Redis set before processing. Duplicate deliveries are detected and discarded at the application layer. This is a well-understood pattern that trades a small amount of application complexity for the ability to use a simpler, ops-light broker.

## Consequences

### Pros

1. **Zero new infrastructure.** Redis is already in our stack, monitored, and on-call. No new process to manage, no new failure mode for on-call to learn.
2. **Fast time-to-value.** Team can implement the async producer/consumer pattern within days, not weeks. Redis Streams' API is small (XADD, XREADGROUP, XACK, XPENDING, XCLAIM) and well-documented.
3. **Consumer groups built-in.** XREADGROUP gives us partitioned, load-balanced consumption across our 4 web servers without external coordination.
4. **Retry and dead-letter support.** XPENDING + XCLAIM enables exponential-backoff retry for failed deliveries. Messages that exceed a retry limit move to a dead-letter stream — solving the silent failure problem.
5. **Sufficient performance at scale.** Redis Streams handle 1M+ messages/s on a single node. Our 10x growth target (~5,000 msg/s peak) is well within headroom, even with persistence enabled (AOF or RDB).
6. **Real-time readiness.** The same Redis instance can serve as a pub/sub backbone for WebSocket push (via Redis Pub/Sub or Streams as a buffer), avoiding a second infrastructure investment when that feature ships.

### Cons

1. **Exactly-once is application-level, not broker-level.** Redis Streams provide at-least-once delivery. True exactly-once requires the idempotency-key pattern described above, which adds code complexity and a small storage overhead per billing event.
2. **Retention is manual.** Kafka retains messages by time or size policy automatically. With Redis Streams we must configure MAXLEN or MINID and prune old entries, or memory grows unbounded. This is straightforward but requires discipline.
3. **No native partitioning beyond consumer groups.** Kafka offers partition-based ordering guarantees (order within partition, parallel across partitions). Redis Streams order all messages in a single stream. For our use case — notifications keyed by project or user — consumer-group ordering is sufficient, but a future high-throughput, strict-per-key ordering requirement might outgrow the model.
4. **Single-node risk.** Our current Redis is not clustered. If it goes down, the notification backlog halts. Mitigated by AOF persistence and a fast failover plan, but this is a real availability gap compared to Kafka's distributed commit log.
5. **Limited tooling ecosystem.** Kafka has a mature ecosystem (schema registry, Connect, ksqlDB). Redis Streams has none of that. If we later need stream processing, schema enforcement, or complex routing, we will build it ourselves or migrate.

## Alternatives Considered

### Apache Kafka

**Why it was the stronger technical fit on paper:**
- Native exactly-once semantics (idempotent producers + transactional consumers in 0.11+), removing the need for application-level dedup on billing events.
- Infinite retention by default; messages are a commit log, not an ephemeral queue.
- Built-in partitioning gives per-key ordering with parallel throughput.
- Rich ecosystem: Schema Registry for contract evolution, Kafka Connect for sink integrations, tooling for monitoring and replay.

**Why we rejected it for this team at this time:**
1. **Operational overhead disproportionate to our scale.** Kafka requires ZooKeeper (or KRaft in newer versions), broker configuration, partition planning, and ongoing tuning. Our team of 6 has no Kafka experience and no dedicated infra engineer. A misconfigured Kafka cluster is a production incident waiting to happen.
2. **2-week delivery constraint is not feasible.** Standing up Kafka, learning its operational model, building the producer/consumer integration, setting up monitoring, and hardening the deployment would take 4–6 weeks minimum for this team. Redis Streams integration can ship in under 2 weeks.
3. **Budget.** Managed Confluent Cloud at our target throughput (5k+ msg/s sustained, with retention and consumer groups) would cost significantly more than self-hosted or managed Redis — which we already pay for.
4. **Overkill throughput.** Kafka's design point is 100k+ msg/s with multi-terabyte backlogs. We need 5k msg/s at peak with modest retention. The operational tax is not justified by the workload.
5. **Migration friction.** Introducing Kafka means a new dependency that all notification producers and consumers must learn. Redis Streams use the same Redis client library the team already imports.

**Revisit if**: Traffic exceeds ~50k msg/s sustained, we need multi-service event sourcing with strict partition ordering, or the team grows to include dedicated platform/infra engineers and can invest in Kafka operations. At that point, the migration path is clear: produce to both Kafka and Redis Streams in parallel, cut over consumers, then retire the Redis Streams producer.