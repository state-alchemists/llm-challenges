# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, peak ~500 req/s) currently sends emails and webhooks synchronously inside the Flask HTTP request cycle. This has caused request timeouts (avg 800ms, spikes to 8s), silent failures with no retry, cascading failures (slow webhooks exhausting connection pools), and zero delivery guarantees for billing-critical notifications.

We must decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (and exactly-once for billing events), and lay the groundwork for real-time WebSocket push within two quarters. The solution must handle 10x traffic growth (~5,000 req/s peak) without re-architecting.

**Constraints**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis is already operational (sessions, rate limiting).
- No prior Kafka experience on the team.
- Maximum 2 weeks of setup/migration work before delivering production value.
- Modest budget; managed Confluent Cloud is not affordable at scale.
- Exactly-once semantics are mandatory for billing notifications.

## Decision

We will use **Redis Streams** as the backbone of the notification subsystem.

**Justification**

1. **Operational complexity.** The team already runs Redis in production and understands its failure modes, monitoring, and backup strategy. Introducing a self-hosted Kafka cluster would require the team to acquire deep expertise in broker tuning, partition rebalancing, replication, and ZooKeeper/KRaft management—activities that are impractical without a dedicated infrastructure engineer and that would blow the 2-week migration window.

2. **Throughput.** Redis Streams is an in-memory data structure. Even at our 10x growth target (~5,000 messages/second peak), this throughput is trivial for Redis and leaves headroom for further growth. A single Redis node can sustain hundreds of thousands of operations per second.

3. **Ordering guarantees.** Redis Streams provides strict, total ordering of messages within a single stream. For notifications tied to a task or user, this lets us consume events in the exact order they were produced, avoiding race conditions where an older status update overwrites a newer one.

4. **Message retention.** Redis Streams supports trimming via `XTRIM` and `MAXLEN`. Notification messages are short-lived by nature (hours to days); once processed and archived to PostgreSQL, they can be safely trimmed. This keeps memory usage bounded while satisfying our retention needs.

5. **Consumer groups.** Redis Streams has native consumer-group support (`XREADGROUP`, `XPENDING`, `XACK`). This gives us horizontal scaling of notification workers, automatic message distribution, and visibility into pending deliveries. While less feature-rich than Kafka's consumer groups, they are fully sufficient for our use case.

6. **Exactly-once semantics for billing.** Redis Streams guarantees **at-least-once** delivery. To satisfy the hard requirement for exactly-once billing notifications, we will implement **application-level idempotency**: every billing event will carry a unique idempotency key, and consumers will record processed keys in PostgreSQL with a unique constraint before emitting the notification. This approach is reliable because the team already has deep PostgreSQL expertise, and it avoids the operational risk of configuring Kafka transactions and idempotent producers correctly.

7. **Real-time roadmap alignment.** Because Redis is already part of our stack, using Redis Streams (and optionally Redis Pub/Sub) for the WebSocket push layer in the next two quarters introduces no new infrastructure dependencies.

## Consequences

### Pros
- **Fast time-to-value.** The subsystem can be built and migrated within the 2-week window because the infrastructure is already in place.
- **Low operational risk.** The team knows how to monitor, back up, and fail-over Redis. No new operational runbooks are required.
- **Cost efficient.** Uses existing Redis capacity; no additional broker licensing or hardware spend.
- **High throughput with low latency.** In-memory processing keeps enqueue and dequeue times in the sub-millisecond range, eliminating the current 800ms–8s HTTP blocking penalty.
- **Simplified architecture.** One less persistent store to manage; archiving to the existing PostgreSQL instance covers audit requirements.

### Cons
- **Memory-bound retention.** If message volume spikes unexpectedly and trimming is misconfigured, Redis memory pressure could affect sessions and rate limiting. We must implement strict `MAXLEN` policies and monitoring alerts.
- **Application-level exactly-once burden.** Billing consumers must correctly implement idempotent de-duplication. A bug in the consumer could lead to duplicate notifications.
- **Less mature stream-processing ecosystem.** Unlike Kafka, there is no rich ecosystem of connectors (e.g., Kafka Connect) or stream-processing frameworks (e.g., Kafka Streams, ksqlDB). If our needs evolve into complex stream joins or windowed aggregations, we may need to introduce another technology later.
- **Durability model.** Redis defaults to asynchronous snapshots (RDB) and optional AOF. In a catastrophic failure scenario, a small window of unacknowledged stream messages could be lost. We will mitigate this with `appendfsync everysec` and off-node backups.

## Alternatives Considered

### Apache Kafka

Kafka was rejected.

- **Operational complexity is disproportionate to our team size.** Running a production Kafka cluster requires expertise in partition planning, replication factor tuning, broker maintenance, and failure recovery. Our 6-person team has no Kafka experience and no infrastructure specialist to own this operational load.
- **Budget constraints rule out managed Kafka.** We cannot afford managed Confluent Cloud at full scale. Self-hosting on AWS (e.g., MSK) still introduces new infrastructure costs and operational surface area.
- **Time-to-value exceeds the 2-week limit.** Standing up a correctly configured Kafka cluster, integrating a Python client, implementing consumer-group logic, and writing operational runbooks would likely take longer than two weeks for an inexperienced team.
- **Exactly-once semantics are native but not free.** Kafka's idempotent producers and transactions solve exactly-once delivery, but configuring and debugging them requires expertise. The operational risk of misconfiguration outweighs the benefit for our current scale, especially when application-level idempotency on PostgreSQL achieves the same business outcome with lower infrastructure risk.

While Kafka offers superior log-based retention, a richer ecosystem, and theoretically unbounded horizontal scaling, these advantages are not worth the operational and learning-curve costs given our constraints and traffic profile.
