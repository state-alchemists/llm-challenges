# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails and webhooks for task updates, assignments, completions, and billing events — synchronously inside the HTTP request cycle. This has caused request timeouts (800ms average, 8s spikes), silent failures with no retry or dead-letter queue, two cascading outages from slow webhook endpoints exhausting the connection pool, and no delivery guarantees for billing-critical notifications.

We need to decouple notification production from delivery, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), prepare for real-time WebSocket push within two quarters, and absorb 10x traffic growth without re-architecting.

Constraints shaping this decision:

- **6-person team** (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Redis already in production** for sessions and rate limiting; the team has operational familiarity.
- **No Kafka experience** on the team today.
- **2-week window** to deliver value before the next production incident compounds.
- **Modest budget** — managed Confluent Cloud at scale is not affordable.
- **Exactly-once semantics required** for billing notifications (trial expiry, payment failure).

Two candidates are evaluated: Apache Kafka and Redis Streams.

## Decision

**Choose Redis Streams.**

Redis Streams meets the throughput, ordering, and consumer-group requirements at our current and 10x projected scale, while fitting the team's expertise and time constraints. The exactly-once requirement for billing notifications is satisfied at the application layer using idempotency keys persisted in PostgreSQL — a pattern the team can implement and reason about within the 2-week delivery window.

Kafka's strengths (durable log, native exactly-once semantics, arbitrarily long retention) are real but over-qualified for this problem today. Its operational cost — cluster management, partition rebalancing, ZooKeeper/KRaft — would consume the team's limited capacity and exceed the delivery window before producing value.

## Consequences

### Pros

- **Fast time to value.** Redis is already running; the team can add streams, consumer groups, and a worker process in days rather than weeks. The 2-week constraint is met with margin.
- **Low operational overhead.** No new infrastructure to provision, monitor, or patch. Redis Sentinel or a managed Redis (ElastiCache) provides the HA we need without adding a dedicated infra role.
- **Adequate throughput.** Redis Streams handles well over 100K messages/s on a single node. Our 10x projected peak (~5K req/s) leaves two orders of magnitude of headroom. Re-architecting is not required.
- **Consumer groups built-in.** `XREADGROUP`, `XPENDING`, and `XCLAIM` give us the same logical model as Kafka consumer groups — multiple workers, claimed messages, pending-entry tracking for retry — without the rebalancing complexity.
- **Per-stream ordering.** Within a single stream, messages are strictly ordered by ID (timestamp + sequence). Partitioning by notification type (billing, task, webhook) preserves order where it matters.
- **Retry with backoff.** Pending messages that exceed a visibility timeout are reclaimed via `XCLAIM` with a configurable idle threshold. Exponential backoff is implemented in the worker loop, not the broker.
- **Team fluency.** The team already operates Redis in production. Diagnosing latency, memory, and eviction is a known domain.

### Cons

- **No native exactly-once semantics.** Redis Streams provide at-least-once delivery. Exactly-once for billing notifications requires application-level idempotency — we will store an idempotency key (e.g., `billing:{event_type}:{entity_id}`) in PostgreSQL and check it before processing. This is a standard pattern but shifts correctness logic into application code and tests.
- **Limited message retention.** Redis Streams use `MAXLEN` or time-based trimming; they are not a durable long-term log. For notifications — where processing happens within seconds to minutes and failures are retried within hours — this is acceptable. Systems that need weeks of event replay will need a separate archive mechanism (e.g., writing to S3 or a data warehouse).
- **Single-node risk without HA.** A standalone Redis instance is a SPOF. We must run Redis Sentinel or migrate to a managed Redis (ElastiCache) with automatic failover before relying on streams for critical notifications. This is straightforward but is additional work.
- **Scaling ceiling.** At traffic levels far beyond 10x (tens of thousands of req/s with large payloads), Redis memory and single-threaded networking become limiting. If the platform eventually reaches that scale, migrating to Kafka becomes the right next step — but not today.
- **No built-in schema registry.** Message format is agreed-upon in application code. Schema evolution must be handled in the consumer (defensive parsing, versioned payloads) rather than enforced by the broker.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard durable log with the strongest guarantees:

- **Throughput**: Scales to millions of messages/s across a cluster. Overkill for our current and near-term scale.
- **Exactly-once semantics**: Idempotent producers and transactional consumers provide EOS natively. This would remove the need for application-level idempotency on billing events — a genuine advantage.
- **Retention**: Configurable retention (hours to weeks) with replay from any offset. Valuable for debugging and audit, though our notification use case processes events promptly.
- **Consumer groups**: Mature, with automatic partition rebalancing and offset management.

**Why rejected:**

1. **Operational complexity exceeds team capacity.** A production Kafka cluster requires broker management, partition planning, KRaft/ZooKeeper, monitoring, and on-call expertise. A 6-person team without a dedicated infra engineer and no prior Kafka experience cannot operate it reliably within 2 weeks.
2. **Budget constraint.** Self-hosted Kafka trades operational cost for license savings; managed Confluent Cloud is priced per partition-hour and per GB egress, which becomes expensive at scale. Our budget cannot absorb either option comfortably today.
3. **Time to value.** Setting up Kafka, learning its client libraries, implementing producers/consumers, and hardening the deployment would take 4–6 weeks minimum for this team — well beyond the 2-week delivery window, during which another cascading outage is likely.
4. **Premature optimization.** Kafka's advantages — unbounded retention, cluster-level scaling, native EOS — solve problems we do not yet have. Redis Streams handles our 10x growth target with headroom to spare. Migrating to Kafka later, if and when the scale demands it, is a cleaner path than adopting it prematurely.

**Migration path:** If the platform reaches a scale where Redis Streams' limitations bind (multi-datacenter replication, retention beyond hours, throughput beyond ~100K msg/s), we can introduce Kafka for the notification stream and migrate consumers incrementally. The consumer-group abstraction in our worker code should be broker-agnostic, making this transition straightforward.