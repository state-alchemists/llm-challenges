# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users with ~2M tasks created per month and a peak of ~500 requests per second. Notifications (emails, webhooks) are currently processed synchronously inside the HTTP request cycle, causing request timeouts (average 800 ms, spiking to 8 s), silent delivery failures with no retry, and two incidents this year where slow webhook endpoints exhausted the database connection pool and cascaded into unrelated feature outages.

Billing-critical notifications—trial expirations, payment failures—require exactly-once delivery semantics. General notifications require at-least-once delivery with retry and exponential backoff. We also plan to add real-time WebSocket push notifications within two quarters and must handle 10× traffic growth without re-architecting.

Key constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Existing stack**: Redis already in production for session storage and rate limiting.
- **Experience gap**: No one on the team has operational Kafka experience.
- **Timeline**: Must deliver value within 2 weeks of starting migration.
- **Budget**: Modest; managed Confluent Cloud at production scale is not affordable today.

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams provides consumer groups (`XREADGROUP`), persistent entries with `XACK`, configurable retention via `MAXLEN`, and per-stream ordering guarantees—all within an infrastructure the team already operates. It meets our throughput requirements comfortably (Redis handles well over 100,000 ops/s on a single node; our peak notification rate is a fraction of that, even at 10× growth). The existing Redis deployment can be extended with minimal operational overhead, and the team can deliver a working async pipeline within the 2-week constraint.

For exactly-once delivery of billing-critical notifications, we will layer an application-level idempotency mechanism on top of Redis Streams' at-least-once guarantee: each billing event producer writes a deterministic ID to a PostgreSQL deduplication table before publishing to the stream, and consumers check this table before processing. This pattern—idempotent consumer + outbox—is well-understood and avoids the operational cost of a full Kafka deployment for the few hundred billing events per day that require the strongest guarantee.

## Consequences

### Pros

- **Fast time to value.** No new infrastructure to provision, configure, or monitor. The team extends an existing Redis deployment and begins shipping async notification processing within days, not weeks.
- **Low operational complexity.** Redis is already on-call runbooks and dashboards. No new broker cluster, no ZooKeeper/KRaft quorum, no partition rebalancing to debug at 2 a.m.
- **Sufficient throughput and ordering.** Redis Streams deliver per-stream strict ordering and comfortably exceed our projected 5,000 msg/s at 10× growth. Consumer groups (`XREADGROUP`) distribute work across workers with built-in claim-and-retry for failed messages.
- **Idempotent billing delivery.** The PostgreSQL outbox + dedup pattern gives us exactly-once processing for billing events without requiring a transactional message broker. This is the same pattern used by Stripe and other payment processors.
- **WebSocket path.** Redis Pub/Sub can be layered alongside Streams for real-time fan-out to WebSocket gateway servers—the same Redis instance, no new infrastructure.
- **Cost containment.** No additional managed-service fees. Memory and persistence for the streams add negligible overhead to the existing Redis instance.

### Cons

- **No native exactly-once semantics.** Redis Streams provide at-least-once delivery. Exactly-once for billing events is achieved through the application-level dedup layer, which adds schema and code complexity. If the dedup logic has a bug, billing notifications could be processed twice.
- **Retention is memory-bound.** Stream entries occupy Redis memory until trimmed via `MAXLEN` or `XTRIM`. Long retention on high-volume streams requires careful capacity planning. We mitigate this by trimming general notification streams to the last 10,000 entries and persisting billing events to PostgreSQL before acknowledgment.
- **Limited tooling ecosystem.** Kafka Connect, Kafka Streams, Schema Registry, and mature monitoring dashboards have no Redis Streams equivalents. If we later need event replay across long time windows or complex stream processing topologies, Redis Streams will require custom tooling.
- **Single-node availability.** Our current Redis setup is not clustered. A Redis node failure would pause all notification processing until failover. This is acceptable given our current HA posture (Redis persistence + quick restart), but must be addressed if the notification subsystem becomes business-critical beyond its current scope.
- **Scale ceiling.** Redis Streams top out at roughly the memory and network limits of a single Redis node (or cluster shard). At true high-volume event streaming—millions of messages per second with multi-day retention—Kafka's distributed log architecture is superior. Our 10× growth target (5,000 msg/s) stays well within Redis's envelope, but a 100× scenario would force a migration.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming. It offers native exactly-once semantics via idempotent producers and transactional consumers, virtually unlimited retention with log compaction, and a rich ecosystem (Connect, Streams, Schema Registry).

**Why we reject it for now:**

- **No team experience.** None of the six engineers has operated Kafka in production. Introducing it means a steep learning curve for broker configuration, partition strategy, consumer lag monitoring, and operational troubleshooting—risk we cannot absorb without a dedicated infrastructure engineer.
- **Operational overhead.** Even in KRaft mode (no ZooKeeper), a production Kafka cluster requires at least three brokers for fault tolerance, plus monitoring, alerting, and capacity planning. This is disproportionate to our current problem: decoupling ~500 req/s of notification work.
- **Timeline risk.** Provisioning, hardening, and onboarding on Kafka will exceed the 2-week value delivery constraint. Redis Streams can be in production within 3–5 days.
- **Budget.** Managed Confluent Cloud at our throughput tier costs significantly more than the incremental Redis memory we need. Self-managed Kafka on EC2 trades money for engineering time we do not have.

Kafka becomes the right choice if we hit scaling limits with Redis Streams (roughly: sustained throughput above 50,000 msg/s, multi-day event retention requirements, or a need for a broader event-driven architecture spanning multiple domains). At that point, we would have the engineering headcount and operational maturity to adopt it responsibly. We can also adopt a hybrid model—keep Redis Streams for real-time fan-out and short-lived notification queues, and introduce Kafka for long-lived event sourcing if the platform evolves toward CQRS or event-driven domain boundaries.

### Redis Pub/Sub (alone)

Redis Pub/Sub provides fire-and-forget fan-out with no persistence, no consumer groups, and no delivery guarantees. It would solve the decoupling problem but not the retry, durability, or exactly-once requirements. Rejected because it cannot meet the core constraint of guaranteed delivery for billing events.

### RabbitMQ

RabbitMQ offers message acknowledgment, dead-letter queues, and retry with TTL—closer to our requirements than Pub/Sub. However, it is a new piece of infrastructure for the team, lacks Kafka's exactly-once semantics, and provides weaker throughput than Redis Streams for our fan-out pattern. Adding RabbitMQ introduces operational complexity comparable to Kafka without the long-term scaling advantage. Rejected in favor of Redis Streams' lower operational cost and existing team familiarity.