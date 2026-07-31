# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project-management platform serves 85,000 monthly active users and peaks at ~500 req/s. Notifications (emails, webhooks) are currently processed synchronously inside the HTTP request cycle. This causes:

- **Request timeouts** — average notification latency is 800 ms, spiking to 8 s during peak hours.
- **Silent failures** — downstream provider outages drop notifications with no retry or dead-letter mechanism.
- **Cascading failures** — slow webhook endpoints have exhausted connection pools twice this year, degrading unrelated features.
- **Missing delivery guarantees** — billing-critical events (e.g., "payment failed") must be delivered exactly once, but the current code provides no such guarantee.

We must decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (and exactly-once for billing events), and support 10× traffic growth without re-architecting. We also plan to add real-time WebSocket push notifications within two quarters.

Our constraints are:
- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Experience**: We already operate Redis (sessions, rate limiting); no one on the team has production Kafka experience.
- **Time**: We must start delivering value within two weeks; we cannot spend a quarter building streaming infrastructure.
- **Budget**: Modest; managed Kafka (Confluent Cloud, MSK Serverless at scale) is not affordable today.

## Decision

**We will use Redis Streams as the messaging layer for the notification subsystem.**

Redis Streams is built into Redis ≥5.0 and is already available in our production environment. It gives us the async decoupling, consumer-group semantics, and retry scaffolding we need while fitting our operational reality.

### Justification

| Criterion | Redis Streams | Apache Kafka (self-hosted) |
|---|---|---|
| **Operational complexity** | Low — we already run Redis, monitor it, and have runbooks. Adding Streams is a configuration change, not a new platform. | High — requires a broker cluster (KRaft or ZooKeeper), partition tuning, replication-factor management, and careful OS-level tuning (page cache, file descriptors, GC). |
| **Time to value** | Days — our existing Redis client libraries support Streams; we can ship a consumer group and retry loop within the first sprint. | Weeks to months — the team must learn broker operations, client semantics, and failure modes before going to production safely. |
| **Throughput** | Sufficient for our target — Redis Streams on a single AWS `cache.r6g.xlarge` can sustain >100,000 messages/s, an order of magnitude above our 10× target of ~5,000 req/s. | Higher theoretical throughput and better horizontal scaling via partition splitting, but we do not need that headroom today. |
| **Ordering guarantees** | Strong per-stream ordering — messages are appended to an immutable log per stream. | Strong per-partition ordering — a mature, well-documented model. Both meet our needs. |
| **Message retention** | Configurable via `MAXLEN` or `MINID` trimming and Redis memory policies. Retention is memory-bound, not disk-bound. | Durable, disk-backed log with time-based or size-based retention; effectively unlimited retention without memory pressure. |
| **Consumer groups** | Native — `XREADGROUP` provides automatic rebalancing, claim-on-failure, and pending-entry inspection for dead-letter logic. | Native and battle-tested at massive scale; more sophisticated rebalancing protocol. |
| **Exactly-once semantics** | At-least-once by default. Exactly-once requires application-level idempotency (deduplication keys in PostgreSQL). | Stronger exactly-once primitives — idempotent producers and transactions across partitions. |

**Why Redis Streams wins for us:**
1. **Team bandwidth is our scarcest resource.** With no infrastructure engineer, self-hosting Kafka introduces a single point of operational failure that could dwarf the bugs we are trying to fix. We already have Redis expertise, dashboards, and alerting.
2. **The 2-week deadline is a hard business constraint.** Redis Streams lets us move notification processing out of the request path and ship retry logic in days. Kafka would consume the entire runway before we delivered a single async notification.
3. **Throughput headroom is adequate.** Our 10× growth target (~5,000 req/s) is well within Redis Streams’ capacity on a single instance. If we eventually outgrow it, the system will already be fully async with retry and idempotency logic, making a later migration to Kafka straightforward.
4. **Exactly-once for billing is achievable.** We will store processed billing notification IDs in PostgreSQL with a unique constraint. Consumer acks are idempotent by key; duplicates become no-ops. This is a standard, well-understood pattern that does not require Kafka’s transaction API.
5. **Future WebSocket work is synergistic.** The same Redis deployment will power pub/sub for real-time WebSocket pushes, amortizing operational cost across two features.

## Consequences

### Pros
- **Fast migration** — We can start moving notifications async within days because Redis is already in the stack.
- **Low operational risk** — Existing monitoring, backups, and runbooks apply. No new failure domain.
- **Cost-efficient** — Runs on our current Redis node; no additional infrastructure spend.
- **Dual use for WebSockets** — The same cluster will later support real-time pub/sub for WebSocket pushes.

### Cons
- **Exactly-once is application-level** — We must build and maintain idempotency keys in PostgreSQL for billing events. This adds a small amount of application complexity and an extra write per billing notification.
- **Memory-bound retention** — Long-term audit trails of all notifications require explicit archival to S3/PostgreSQL; we cannot retain months of history in Redis Streams without provisioning excessive memory.
- **Harder to scale beyond 10×** — If we grow past ~10,000–20,000 sustained notifications/s, we will need Redis Cluster or a migration to Kafka. We accept this trade-off because our current crisis is latency and reliability, not absolute throughput.
- **Less mature ecosystem** — No Kafka Connect or schema registry equivalent; we will build lightweight Python consumers rather than using off-the-shelf connectors.

## Alternatives Considered

### Apache Kafka (self-hosted or managed)

**Why we rejected it:**
- **Operational overhead exceeds team capacity.** Self-hosting Kafka requires expertise in broker configuration, partition rebalancing, replication under load, and disk management. Our 6-person team does not have this expertise, and hiring or training is not in the current budget or timeline.
- **Managed offerings are too expensive.** Confluent Cloud or MSK at our target scale would strain our modest budget, especially when we already operate Redis.
- **The learning curve conflicts with the 2-week delivery window.** Even with managed Kafka, the client-side semantics (producer acks, consumer rebalancing, exactly-once transaction APIs) require time to learn and test safely. We cannot afford to delay the fix for request timeouts and cascading failures while the team becomes Kafka-proficient.
- **Advantages are latent, not immediate.** Kafka’s superior disk retention, partition scaling, and exactly-once primitives are valuable at much larger scale, but they do not solve our pressing problem (synchronous notification blocking HTTP responses) any faster than Redis Streams does.

If we outgrow Redis Streams in 18–24 months, we will revisit Kafka with the operational runway to run it properly.
