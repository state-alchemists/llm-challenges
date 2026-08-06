# ADR-001 — Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users and generates ~2 million tasks per month. Notifications (emails and webhooks) are currently dispatched synchronously inside the Flask HTTP request cycle. This has caused:

- **Request timeouts**: Average notification latency is 800 ms and spikes to 8 s during peak hours (~500 req/s), degrading the user experience for unrelated endpoints.
- **Silent failures**: If an email provider or webhook target is unreachable, the notification is dropped with no retry, no dead-letter queue, and no audit trail.
- **Cascading failures**: Two production incidents this year were caused by slow webhook endpoints exhausting the PostgreSQL connection pool, bringing down features unrelated to notifications.
- **No delivery guarantees**: Billing-critical events (e.g., "trial expired", "payment failed") must be delivered exactly once, but the current system provides no idempotency or transactional outbox mechanism.

We must decouple notification delivery from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery for all events (and exactly-once for billing events), and lay groundwork for real-time WebSocket push notifications within two quarters. The design must accommodate 10× traffic growth without another re-architecture.

### Constraints

- **Team size**: 6 engineers (3 senior, 3 mid-level); no dedicated infrastructure engineer.
- **Operational baseline**: We already run Redis (ElastiCache) for session storage and rate limiting; the team knows its tuning, monitoring, and backup procedures.
- **Experience gap**: No engineer has operated Kafka in production.
- **Time to value**: The migration must deliver production value within two weeks.
- **Budget**: Modest; managed Confluent Cloud at full projected scale is not affordable today.

## Decision

We will use **Redis Streams** as the persistent message bus for the notification subsystem.

Redis Streams satisfies our throughput requirements—peak load is ~500 messages per second today, and even 10× growth (5,000 msgs/s) is well within the operational headroom of a single Redis instance, which routinely handles 100,000+ ops/s. Because Redis is already a production dependency, the team can provision a dedicated Streams instance (or logically isolated database index) using existing Terraform modules, monitoring dashboards, and runbooks. This keeps the setup and migration window under the two-week constraint while immediately removing notification work from the HTTP request path.

Exactly-once delivery for billing notifications will be enforced at the application layer: consumers write a processed-event ID to PostgreSQL within the same transaction that marks the notification as sent. Redis Streams provides atomic `XADD`/`XREADGROUP`/`XACK` semantics and explicit pending-entry lists, which are sufficient to build at-least-once consumers; the application-level idempotency key closes the gap to exactly-once. This pattern is the same one required even with Kafka (where broker-level exactly-once semantics still leave the consumer side vulnerable to duplicate processing unless the downstream write is idempotent or transactional).

## Consequences

### Positive

- **Fast time to value**: The team can begin migrating notification producers within days because Redis clients, observability, and infrastructure templates are already in place.
- **Low operational burden**: A single additional Redis node (or ElastiCache replica) introduces far fewer moving parts than a Kafka cluster (brokers, ZooKeeper/KRaft, partition rebalancing, separate monitoring stack). A team without a dedicated infrastructure engineer cannot safely self-host Kafka without significant risk.
- **Sufficient headroom**: Redis Streams can absorb our 10× throughput target on a modest instance. If we eventually outgrow it, we can shard by stream key or migrate to a managed streaming service later.
- **Real-time synergy**: Redis pub/sub and Streams can feed the same WebSocket push layer we plan to build next quarter, reusing connection and serialization logic.
- **Cost control**: Managed Redis (ElastiCache) or a self-managed EC2 instance fits the modest budget; we avoid the per-partition, per-GB pricing of managed Kafka at scale.

### Negative

- **Retention is memory-bound**: Unlike Kafka, which retains messages on inexpensive disk for long periods by default, Redis Streams keep data in memory (or rely on AOF/RDB snapshots). We must explicitly configure `MAXLEN` or `MINID` eviction policies and size the instance to hold at least 24–72 hours of messages plus headroom for retries.
- **Consumer-group maturity**: Redis Streams consumer groups lack the automatic partition rebalancing and offset-management sophistication of Kafka. We must handle stalled consumers with `XPENDING` and `XCLAIM` manually, and consumer-failure recovery is slightly more code to maintain.
- **Scaling ceiling**: If message volume grows beyond what a single Redis primary can handle, horizontal sharding by stream name (e.g., `billing_events`, `task_events`) is straightforward but not as transparent as Kafka partition scaling. We accept this trade-off because our 10× target is safely inside single-node capacity.
- **No built-in exactly-once across streams**: We must implement idempotency in application code (deduplication table in PostgreSQL). This adds a small schema migration and requires careful transactional boundaries in the consumer workers.

## Alternatives Considered

### Apache Kafka

Kafka was rejected because the operational and experiential costs outweigh the benefits for our current scale and team constraints.

- **Operational complexity**: A production Kafka cluster requires at least three brokers plus ZooKeeper or KRaft controllers, partition planning, replication-factor tuning, and a separate monitoring toolchain. Our 6-person team has no Kafka expertise and no infrastructure engineer to own on-call rotation for it. Self-hosting Kafka under these conditions poses an unacceptable risk of incidents and pager fatigue.
- **Setup timeline**: Standing up a secure, monitored, backed-up Kafka cluster and updating producers/consumers would consume more than the two-week window before delivering value.
- **Cost**: Managed options (Confluent Cloud, MSK) exceed our modest budget at the projected scale. The alternative is self-hosting, which returns us to the operational-complexity problem above.
- **Throughput overkill**: Kafka’s durability, partition scaling, and disk-based retention are superior, but they solve a problem we do not yet have. Our peak throughput is three orders of magnitude below the point where Kafka’s architectural advantages become load-bearing.

Kafka would become the right choice if our message volume exceeded the single-node capacity of Redis (roughly >50,000 sustained msgs/s with persistence), if we required multi-year log retention for compliance, or if the team grew to include infrastructure engineers with Kafka operational expertise. At that point we would re-evaluate with a new ADR.
