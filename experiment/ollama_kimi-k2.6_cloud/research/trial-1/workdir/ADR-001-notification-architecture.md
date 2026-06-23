# ADR-001: Notification Architecture

## Status

Proposed

## Context

The notifier subsystem in our SaaS project management platform currently processes emails and webhooks synchronously inside the HTTP request cycle. At 85,000 monthly active users, ~2M tasks created per month, and peak loads of ~500 req/s, this design has become untenable. We experience average notification latencies of 800ms, spikes to 8s during peak hours, silent failures with no retry mechanism, and cascading failures that have caused two production incidents this year due to connection pool exhaustion.

Our scaling targets require us to:

- Decouple notifications from the HTTP request cycle via asynchronous processing.
- Support retry with exponential backoff and a dead-letter mechanism.
- Guarantee at-least-once delivery for all events, with exactly-once semantics for billing-critical notifications (e.g., "trial expired", "payment failed").
- Lay the groundwork for real-time WebSocket push notifications within two quarters.
- Support 10x traffic growth (peak ~5,000 req/s) without a subsequent re-architecture.

We operate under tight operational constraints:

- **Engineering team**: 6 people (3 senior, 3 mid-level), with no dedicated infrastructure engineer.
- **Existing stack**: Python/Flask monolith, PostgreSQL, AWS, and Redis (currently used for session storage and rate limiting).
- **Experience gap**: No team member has production experience operating Apache Kafka.
- **Timeline**: We must deliver value within two weeks; setup and migration cannot exceed this window.
- **Budget**: Modest. We cannot afford managed Confluent Cloud at full scale today.

Given these constraints, we must select a message broker that balances immediate deliverability, operational safety, and long-term scaling headroom.

## Decision

We will adopt **Redis Streams** as the backing message broker for the notification subsystem.

This decision is driven by the intersection of our functional requirements and operational constraints. While Apache Kafka offers superior raw throughput and native exactly-once semantics, the operational complexity of self-hosting Kafka—combined with our lack of in-house expertise and our two-week delivery mandate—introduces an unacceptable risk of misconfiguration, delayed delivery, and ongoing maintenance burden for a six-person team without infrastructure specialists.

Redis Streams meets our throughput requirements: even at 10x growth (~5,000 req/s peak), this is well within the operational capacity of a single Redis instance, which routinely handles 100,000+ operations per second. Our existing Redis infrastructure (already used for sessions and rate limiting) means the team can leverage familiar tooling, monitoring, and failover patterns, keeping the operational surface area minimal.

To satisfy the exactly-once requirement for billing notifications, we will implement **application-layer idempotency** rather than relying on broker-native semantics. Every billing event will carry a unique idempotency key. Consumer workers will check this key against a deduplication table in PostgreSQL (using an atomic `INSERT … ON CONFLICT DO NOTHING` pattern) before emitting the notification. Redis Streams’ acknowledgment mechanism (`XACK`) combined with consumer groups (`XREADGROUP`) provides at-least-once delivery; the PostgreSQL deduplication layer upgrades this to effectively exactly-once for billing-critical events. This approach is robust because the side effects of notification delivery (email sends, webhook POSTs) are external to any message broker and require application-level idempotency regardless of the underlying technology.

## Consequences

### Positive

- **Rapid time to value**: Redis Streams can be integrated into our existing Python/Flask stack within days using standard Redis client libraries. There is no new infrastructure to provision, no new operational runbooks to write, and no team training required.
- **Operational continuity**: The team already monitors, backs up, and maintains Redis. Adding Streams is a data-type change, not a new system. This minimizes the risk of on-call incidents caused by unfamiliar failure modes.
- **Sufficient throughput headroom**: At our target peak of ~5,000 req/s, Redis Streams (backed by Redis’s single-threaded event loop) is comfortably within performance limits. We can vertically scale the instance or shard by notification type if necessary.
- **Natural WebSocket path**: Our planned real-time push notification layer can reuse the same Redis infrastructure via Pub/Sub or Stream fan-out, avoiding the introduction of yet another middleware component.
- **Cost efficiency**: We incur no additional licensing or managed-service costs. We can run Streams on our existing Redis instances or spin up a modest AWS ElastiCache cluster using established patterns.

### Negative

- **Memory-bound retention**: Redis is primarily an in-memory data store. Stream entries are subject to eviction if memory limits are reached. We must configure explicit stream trimming (`MAXLEN` or `MINID`) and size our instance carefully to prevent message loss during extended outages. Long-term replay or audit trails are better served by PostgreSQL or S3.
- **Exactly-once is application-level**: Unlike Kafka’s native EOS (exactly-once semantics) with idempotent producers and transactional commits, Redis Streams only guarantees at-least-once delivery. The burden of deduplication falls on our application code. A bug in the idempotency logic could lead to duplicate billing notifications.
- **Less mature consumer group rebalancing**: Redis Streams consumer groups (`XREADGROUP`) support failover and partitioning, but the rebalancing protocol is less sophisticated than Kafka’s. During consumer scaling events or deployments, we may see temporary duplicate processing until consumers stabilize, reinforcing the need for the PostgreSQL deduplication guard.
- **Single-threaded bottleneck**: While 5,000 req/s is manageable, complex stream processing logic (e.g., large message payloads, heavy Lua scripts) could consume the main Redis thread. We must keep message payloads small and processing logic lightweight, offloading heavy work to the Flask worker tier.
- **Durability gap**: Redis persistence (AOF/RDB) protects against process restarts but is not equivalent to Kafka’s replicated, disk-backed commit log. A catastrophic failure of the Redis primary before an `XACK` is persisted could result in re-delivered messages upon recovery.

## Alternatives Considered

### Apache Kafka

We rejected Apache Kafka as the primary broker for this phase.

Kafka offers industry-leading durability, partition-based ordering, and native exactly-once semantics via idempotent producers and transactional APIs. Its replicated commit log and consumer group protocol are more robust than Redis Streams for large-scale, long-retention event sourcing.

However, Kafka’s advantages are outweighed by our constraints:

- **Operational complexity**: Self-hosted Kafka requires managing a ZooKeeper or KRaft quorum, broker discovery, partition rebalancing, ISR (in-sync replica) management, and careful JVM tuning. This is not a two-week task for a team with zero Kafka experience and no infrastructure engineer.
- **Learning curve**: The team would need to become proficient with Kafka producer/consumer configurations, exactly-once tuning, monitoring (JMX metrics), and failure recovery before production deployment. This conflicts with our mandate to deliver immediate value.
- **Budget constraints**: Managed options such as Confluent Cloud or AWS MSK would offload operational burden but at a significant recurring cost. The context explicitly states that managed Confluent Cloud is unaffordable at full scale today. AWS MSK Serverless is cheaper but still introduces non-trivial costs and requires Kafka client expertise.
- **Overkill for current scale**: Our throughput target of ~5,000 req/s is modest by Kafka standards. We would be paying a heavy operational tax for headroom we do not yet need.

We acknowledge that Kafka may become the right choice if we outgrow Redis Streams or if we hire dedicated infrastructure expertise. We will revisit this decision if we exceed Redis’s throughput or retention limits, or if we require multi-region replication. For the current phase, Redis Streams is the correct risk-adjusted choice.
