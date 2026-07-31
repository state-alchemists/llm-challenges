# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

**Status:** Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, ~500 req/s peak) processes all notifications — emails, webhooks, and soon WebSocket pushes — synchronously inside the HTTP request cycle. This has caused request timeouts (800ms avg, 8s spikes), silent failures with no retry or dead-letter queue, two cascading outages from slow webhook endpoints exhausting the connection pool, and zero delivery guarantees for billing-critical notifications that require exactly-once semantics.

We need to decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), support real-time WebSocket pushes within two quarters, and absorb 10x traffic growth without re-architecting.

Key constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Timeline**: Must deliver value within 2 weeks of starting migration.
- **Current stack**: Python/Flask monolith, PostgreSQL, Redis already in production (sessions + rate limiting).
- **Budget**: Modest; managed Confluent Cloud at full scale is not affordable.
- **Kafka experience**: None on the team today.
- **Billing requirement**: Exactly-once semantics for billing notifications.

## Decision

**Use Redis Streams** as the notification subsystem's message broker.

Redis Streams is the right choice because the dominant constraint is not raw throughput ceiling — it is time-to-value and operational sustainability for a small team with no infrastructure specialist. Redis is already in our stack, the team is comfortable operating it, and Redis Streams' consumer group model (XREADGROUP, XACK, XPENDING, XCLAIM) provides everything we need for reliable notification delivery at our current and near-term scale.

Exactly-once semantics for billing notifications will be achieved through **application-level idempotency**: each billing notification carries an idempotency key, and the consumer deduplicates against PostgreSQL before performing side effects. This is the same pattern used by Stripe's webhook system and is robust against redeliveries, which Redis Streams will produce under at-least-once semantics.

## Consequences

### Pros

- **Fast time-to-value.** Redis Streams reuse our existing Redis deployment (or a dedicated instance alongside it). No new infrastructure to provision, secure, monitor, or learn. The team can ship the core async decoupling — the change that eliminates request timeouts and cascading failures — within days, well under the 2-week constraint.
- **Low operational complexity.** We already run Redis in production. Adding Streams uses the same operational playbook: the same backup, persistence (AOF/RDB), replication, and monitoring tooling. No ZooKeeper/KRaft cluster, no partition rebalancing, no broker rack awareness to manage.
- **Sufficient throughput.** A single Redis instance handles hundreds of thousands of messages per second. Our 10x growth target (~5,000 req/s peak) is well within this envelope. We would not approach Redis Streams' ceiling until well beyond 50x current scale.
- **Consumer groups are native.** XREADGROUP gives us partitioned consumption, XACK confirms delivery, XPENDING and XCLAIM enable retry of failed messages, and XAUTOCLAIM supports dead-letter evacuation. This is the exact model we need for worker-based notification processing.
- **Ordering guarantees within a stream.** Messages in a Redis Stream are strictly ordered by insertion. Notification events for a given entity (task, project, billing account) can be routed to the same stream or use the same ID prefix to preserve causal ordering.
- **Retention is configurable.** MAXLEN lets us cap stream size to prevent unbounded memory growth; MINID lets us prune by time. This is sufficient for a notification pipeline where processing latency is measured in seconds, not hours.
- **Natural path to WebSocket push.** The same consumer that processes email/webhook notifications can fan out to connected WebSocket clients via Redis Pub/Sub, using our existing Redis instance. No additional broker is required for the real-time push roadmap item.

### Cons

- **No native exactly-once semantics.** Redis Streams provides at-least-once delivery. Exactly-once for billing notifications requires application-level idempotency (idempotency key + PostgreSQL dedup table). This adds a small amount of consumer-side complexity, but it is a well-understood pattern and far simpler than operating Kafka Transactions.
- **Message retention is less flexible than Kafka.** Redis Streams retain messages until explicitly trimmed (MAXLEN/MINID). There is no Kafka-style log-compaction or time-based retention with automatic segment rolling. We must set MAXLEN to prevent unbounded growth, which means consumers that fall behind beyond the retention window will miss messages. Mitigated by setting retention to ~1 hour (far beyond our target p99 processing latency of seconds) and alerting on consumer lag via XINFO GROUPS.
- **Scale ceiling is lower than Kafka.** Redis Streams top out at single-node memory limits and single-threaded command execution per shard. For our 10x target this is immaterial (~5K msg/s is trivial), but if we grew to 100x+ with multi-terabyte backlogs, we would need to re-evaluate. Kafka's distributed log architecture handles that regime natively.
- **Less mature ecosystem tooling.** Kafka has a richer ecosystem (Kafka Connect, schema registry, ksqlDB). Redis Streams has fewer off-the-shelf integrations. We will build small adapter scripts for monitoring and dead-letter replay, but these are straightforward given our Python stack.
- **Single-node or small-cluster topology.** Redis Streams do not shard across nodes transparently the way Kafka partitions across brokers. Scaling beyond a single node requires application-level key routing (e.g., stream-per-entity-type). This is acceptable for our use case — a handful of notification streams is manageable — but it is not the transparent horizontal scaling Kafka offers.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event streaming platform. We evaluated it carefully because its properties are impressive on paper for our stated requirements:

| Property | Kafka | Redis Streams |
|---|---|---|
| Throughput | Millions of msgs/s (distributed) | Hundreds of thousands of msgs/s (single-node) |
| Ordering | Per-partition strict | Per-stream strict |
| Retention | Configurable time/compaction | MAXLEN/MINID trim only |
| Consumer groups | Native, mature (Kafka Connect ecosystem) | Native (XREADGROUP), smaller ecosystem |
| Exactly-once | Idempotent producer + transactions | At-least-once; exactly-once via app-level idempotency |
| Operational complexity | High (brokers, ZooKeeper/KRaft, partitions, monitoring) | Low (reuse existing Redis) |
| Team readiness | None | High |

**Why we rejected Kafka for this decision:**

1. **Setup time exceeds our constraint.** A production Kafka deployment (even with KRaft, eliminating ZooKeeper) requires broker provisioning, topic design, partition planning, monitoring dashboards, and alerting. With no Kafka experience on the team, 2 weeks is unrealistic to ship value — we would spend the entire window on infrastructure before writing a single notification consumer.

2. **Operational burden is unsustainable for our team.** Kafka requires ongoing operational investment: partition rebalancing, broker failures, disk management, and consumer lag monitoring. Our team has no dedicated infrastructure engineer. Adding Kafka means every on-call rotation includes a system nobody has run before, in a domain (distributed consensus) where misconfiguration causes subtle data loss.

3. **Cost.** Self-hosted Kafka on AWS requires minimum 3 broker instances (for replication) plus monitoring infrastructure. Managed Confluent Cloud at our scale starts around $200–400/month and grows with throughput — explicitly called out as unaffordable in our constraints. Running Kafka ourselves trades money for engineering time we don't have.

4. **Exactly-once via Kafka Transactions is not simpler than app-level idempotency.** Kafka's exactly-once semantics require enabling transactions, which add significant operational complexity (transaction coordinator, increased latency, harder consumer configuration). For a notification pipeline where the consumer's side effect is an HTTP call (email/webhook), application-level idempotency with a dedup table is simpler, more debuggable, and independent of the broker.

Kafka is the right choice if we eventually reach a scale where we need a distributed commit log with multi-day retention, cross-service event sourcing, or a data lake ingestion pipeline. That is not the problem we are solving today. The problem is: *decouple notifications, add retry, guarantee delivery, do it in two weeks, and do it with a team of six*. Redis Streams fits that problem; Kafka does not.

---

If traffic grows beyond Redis Streams' comfortable envelope (50x+ current scale) or we adopt event-sourced domain models across services, we should revisit this decision with a new ADR. The consumer-side abstraction (idempotency key + dedup table) is broker-agnostic and will migrate cleanly if we ever switch.