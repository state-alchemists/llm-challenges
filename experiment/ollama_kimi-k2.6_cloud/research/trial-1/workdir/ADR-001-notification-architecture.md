# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform currently sends notifications (email, webhooks) synchronously inside the HTTP request cycle. At 85,000 MAU and a peak of ~500 req/s, this produces average latency of 800 ms and spikes to 8 s during business hours. If an email provider or webhook endpoint is unavailable, the notification is silently dropped with no retry and no dead-letter queue. Two incidents this year occurred when a slow webhook endpoint caused connection pool exhaustion, taking down unrelated features.

We must:

- Decouple notifications from the HTTP request cycle.
- Support retry with exponential backoff.
- Guarantee at-least-once delivery for all notifications; exactly-once for billing-critical events (e.g., "trial expired", "payment failed").
- Lay the groundwork for real-time WebSocket push notifications within two quarters.
- Handle 10× traffic growth without re-architecting.

Our constraints are:

- Engineering team of six (three senior, three mid-level), with no dedicated infrastructure engineer.
- Redis is already in production for session storage and rate limiting.
- No prior Apache Kafka experience on the team.
- The solution must require no more than two weeks of setup and migration work before delivering value.
- Modest budget; managed Kafka offerings (e.g., Confluent Cloud) are not viable at full scale today.

## Decision

We will adopt **Redis Streams** as the backbone of the notification subsystem.

Redis Streams is available in our existing production Redis deployment, so we can introduce a stream and consumer groups incrementally without provisioning new infrastructure or learning a new operational stack. A small team can own it using existing runbooks and monitoring.

For our traffic profile, throughput is not the deciding factor. Redis Streams can sustain **>500,000 messages/s per node**. Our peak of ~500 req/s—even under a 10× growth assumption—represents a tiny fraction of that capacity. Kafka’s raw throughput (millions of messages/s across a cluster) is therefore unused capacity that we would pay for in operational complexity.

**Consumer groups** (`XGROUP`) give us the horizontal scaling and fault tolerance we need. Each worker claims messages, acknowledges them after delivery (`XACK`), and failed deliveries can be retried via the pending list (`XPENDING` followed by `XCLAIM`). This directly satisfies our retry requirement.

**Message ordering** is guaranteed per stream. For events where order matters (e.g., a task reassigned then completed), we route to a single stream key. For unordered notifications, we fan out across multiple stream keys to reduce contention.

**Message retention** will be configured via `MAXLEN` and `XTRIM`, capping each stream to a safe bound (e.g., 1–2 million entries or explicit trimming based on age in application logic). Notifications are transient by nature; long-term audit trails already live in PostgreSQL, so we do not need months of replayable log history.

**Exactly-once semantics** for billing-critical events will be implemented at the application layer rather than the transport layer. Every billing notification carries a deterministic UUID generated from the triggering domain event. The consumer inserts that UUID into an `idempotent_notifications` table in PostgreSQL with a unique constraint before emitting the email or webhook. Redis Streams provides at-least-once delivery; the idempotency table converts that to exactly-once processing. This is simpler and cheaper for our scale than operating Kafka transactions with transactional consumer groups.

**Operational complexity** is the decisive factor. Introducing Apache Kafka would require deploying ZooKeeper or KRaft, tuning brokers, managing partition rebalancing, and monitoring consumer lag—expertise our team does not have and cannot acquire safely inside a two-week deadline. Self-hosted Kafka on EC2 would increase our failure surface, and managed Kafka (MSK) would exceed our modest budget. Redis Streams reuses our existing investment and operational knowledge.

## Consequences

### Pros

- **Fast time-to-value:** The first decoupled notification can be shipped within hours; full migration fits comfortably inside the two-week window.
- **Operational leverage:** We reuse existing Redis expertise, alerting, and backup procedures.
- **Low cost:** No new managed-service spend or additional EC2 instances.
- **Horizontal worker scaling:** Consumer groups allow us to add Python worker processes or containers to drain streams as volume grows.
- **Failure isolation:** Async workers protect the web tier from slow email providers or webhook endpoints.
- **Bounded replayability:** Streams retain messages until explicitly trimmed, allowing us to replay a bounded window if a consumer deployment fails.

### Cons

- **Exactly-once is an application concern:** Bugs in the idempotency table or UUID generation could duplicate sensitive billing notifications.
- **Retention is memory-bound:** If we misconfigure `MAXLEN`, Redis memory can grow unbounded, or we can drop events before they are consumed. Monitoring stream length is a new operational task.
- **Redis criticality increases:** Redis is today used for ephemeral cache data (sessions, rate limiting). Adding a durable workload changes its failure profile. If a Redis node restarts ungracefully, AOF replay can block service startup; we may need to separate the Streams workload onto a dedicated Redis node or cluster.
- **Ecosystem maturity:** Fewer off-the-shelf connectors and tools than Kafka. If we later need Change Data Capture (CDC) or complex stream processing, we will likely need custom consumers or a future migration.
- **Ordering is per-stream:** If we need total order across all notification types in the future, we will need application-level sequencing.

## Alternatives Considered

### Apache Kafka (rejected)

Apache Kafka would provide stronger platform-level guarantees: disk-based log retention (unbounded by memory), strict ordering per partition, and native **exactly-once semantics** via idempotent producers and transactions. It is the industry-standard choice for event-driven systems at scale.

However, for our team and timeline, Kafka is the wrong trade-off:

- **Setup and operational cost:** Self-hosting Kafka requires ZooKeeper or KRaft, broker maintenance, partition rebalancing, and consumer-lag monitoring. With no dedicated infrastructure engineer and a six-person team, this would create a single point of operational fragility.
- **Learning curve:** The team has zero Kafka experience. A production-safe deployment with monitoring, backup, and disaster recovery cannot be built confidently in two weeks.
- **Budget constraint:** Managed Confluent Cloud is explicitly ruled out by our modest budget, and AWS MSK would still add significant fixed cost at full scale.
- **Unused capacity:** Kafka’s throughput advantage is irrelevant at our scale. We would be optimizing for a property we do not need while neglecting the constraint—operational capacity—that we do.

If we outgrow Redis Streams in the future (e.g., multi-year log retention, complex stream joins, or tens of thousands of sustained messages per second become requirements), we will evaluate a managed stream-processing platform as a second-generation architecture.
