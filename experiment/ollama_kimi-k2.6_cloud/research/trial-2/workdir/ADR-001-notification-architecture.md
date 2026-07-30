# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform currently processes notifications synchronously inside the HTTP request cycle. At peak load (~500 req/s), this produces average latencies of 800 ms with spikes to 8 s, and has caused two connection-pool exhaustion incidents this year. Billing-critical notifications (e.g., "payment failed") currently have no delivery guarantee.

We must:

- Decouple notification dispatch from the request cycle.
- Support retry with exponential backoff and a dead-letter mechanism.
- Guarantee at-least-once delivery for all events; exactly-once for billing events.
- Add real-time WebSocket push within two quarters.
- Sustain 10× traffic growth (~5,000 req/s peak) without re-architecting.

Constraints:

- Engineering team of 6 with no dedicated infrastructure engineer.
- Redis already runs in production (sessions, rate limiting).
- No prior Kafka experience.
- Maximum two weeks to set up and begin delivering value.
- Modest budget; managed Confluent Cloud is not viable today.

## Decision

We will adopt **Redis Streams** as the message broker for the notification subsystem.

### Justification

1. **Operational fit and time-to-value.** The team already operates Redis in production. Adding Streams to the existing cluster requires minimal new infrastructure (a larger instance or an additional replica), whereas self-hosting Apache Kafka on AWS (or paying for MSK) would require ZooKeeper/KRaft setup, partition tuning, and operational runbooks the team does not have. The two-week delivery constraint makes Kafka infeasible.

2. **Throughput headroom for 10× growth.** Redis Streams can sustain hundreds of thousands of messages per second on a single node. Our 10× target of ~5,000 req/s is well within that envelope, giving us several years of headroom before partitioning across multiple Redis instances or migrating becomes necessary.

3. **Ordering guarantees.** Redis Streams provides total ordering within a single stream (`XADD` assigns monotonic IDs). This is sufficient for our notification use case: we can use separate streams per notification category (email, webhook, billing) if we need logical parallelism while preserving ordering inside each category.

4. **Consumer groups and retry mechanics.** Redis Streams supports consumer groups (`XREADGROUP`, `XACK`) with automatic ownership tracking of pending messages. Unacknowledged messages can be claimed by other consumers after a timeout (`XPENDING` + `XCLAIM`), enabling straightforward retry and dead-letter logic in our Python workers.

5. **Message retention.** We will configure `MAXLEN` and/or time-based expiry (`XTRIM`) on each stream to bound memory usage. Retention will be set to 7 days for standard notifications and 30 days for billing streams. While this is memory-bound (unlike Kafka's disk-based persistence), our message volumes are small enough (< 1 KB per event) that a modestly sized Redis instance can retain millions of messages without issue.

6. **Exactly-once semantics for billing events.** Redis Streams natively provides at-least-once delivery. For billing-critical notifications, we will implement client-side exactly-once by making consumers idempotent: each worker records the processed Redis stream IDempotently in PostgreSQL (using an `INSERT IGNORE`-style pattern) before performing the external action (e.g., sending the email). This approach is pragmatic, well understood, and avoids the heavy transactional overhead of Kafka's exactly-once producer/consumer APIs.

7. **Future WebSocket push.** Redis Pub/Sub is already available on the same infrastructure. We can layer WebSocket delivery (`PUBLISH` to a channel per user/session) alongside Redis Streams without introducing a second distributed system.

## Consequences

### Pros

- **Fast migration:** We can begin moving notification types off the synchronous path within days, not weeks.
- **Low operational burden:** Uses existing Redis expertise, monitoring, and failover procedures.
- **Cost-effective:** No new managed service fees; only a Redis capacity increase.
- **Unified stack:** Sessions, rate limiting, stream processing, and WebSocket pub/sub all live on one technology.
- **Sufficient throughput:** Current and 10× projected load is trivial for Redis Streams.

### Cons

- **Memory-bound retention:** Long-term archival or very high back-pressure scenarios could force eviction if memory limits are reached. We accept this because our volumes are low and we will monitor memory closely.
- **Weaker exactly-once primitives:** Kafka's idempotent producer and transactions are more robust than client-side idempotency. We mitigate this by isolating billing logic to a small, well-tested worker and auditing delivery via PostgreSQL.
- **Limited stream-processing ecosystem:** There is no Kafka Connect or Kafka Streams equivalent in the Redis ecosystem. Complex transformations will need to be built in application code.
- **Horizontal scaling friction:** If we eventually outgrow a single Redis primary, partitioning streams across shards requires application-level routing. We acknowledge this as a future risk and will instrument throughput and memory metrics to trigger re-evaluation.

## Alternatives Considered

### Apache Kafka

Kafka was rejected because, despite its superior long-term scaling story and stronger exactly-once semantics (idempotent producers, transactions, and log compaction), the operational reality does not match our constraints.

- **Operational complexity:** Self-hosting Kafka requires managing ZooKeeper or KRaft metadata, partition rebalancing, and consumer-offset bookkeeping. Without a dedicated infrastructure engineer, the team would spend disproportionate time on broker tuning and incident response.
- **Time-to-value:** Getting a production-ready Kafka cluster (or MSK instance) with appropriate networking, ACLs, client library configuration, and exactly-once tuning would consume the majority of our two-week budget before a single notification was migrated.
- **Cost:** MSK or self-managed EC2 clusters introduce fixed costs for brokers and storage. Redis leverages existing spend.
- **Team expertise:** Adopting Kafka would place a new, complex technology into the critical path of a small team with no prior experience, increasing the risk of downtime during the migration itself.

We will revisit Kafka if our throughput or retention requirements grow beyond what a single Redis instance can sustain, or if we hire dedicated platform engineering capacity.
