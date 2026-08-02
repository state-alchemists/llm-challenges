# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails, webhooks, and future WebSocket pushes — synchronously inside the HTTP request cycle. This has caused request timeouts (average 800ms, spikes to 8s), silent failures with no retry or dead-letter queue, two cascading-failure incidents from slow webhooks exhausting the connection pool, and no delivery guarantees for billing-critical notifications.

We need to decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), add real-time WebSocket push within two quarters, and handle 10× traffic growth without re-architecting.

Constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infra engineer.
- **Existing stack**: Redis already in production for sessions and rate limiting. Zero Kafka experience on the team.
- **Timebox**: Must deliver value within 2 weeks of starting migration.
- **Budget**: Modest — managed Confluent Cloud at full scale is not affordable today.
- **Correctness**: Billing notifications require exactly-once semantics.

Two candidates are on the table: **Apache Kafka** and **Redis Streams**.

## Decision

**We choose Redis Streams.**

The deciding factor is operational fit. A six-person team with no Kafka experience and no dedicated infra engineer cannot absorb the operational complexity of a Kafka cluster within a two-week delivery window while also delivering the retry and delivery-guarantee features the system urgently needs. Redis Streams provides consumer groups, acknowledged-delivery semantics, message retention, and sufficient throughput for our scale — all on infrastructure the team already operates.

For exactly-once billing notifications, we will layer a **deduplication table in PostgreSQL** (idempotency keys on notification IDs) on top of Redis Streams' at-least-once delivery. This is the standard pattern: the broker guarantees delivery, the application guarantees exactly-once processing. This avoids conflating the broker's delivery semantics with application-level correctness — something even Kafka requires application-side idempotency for in practice.

Redis Streams handles our current 500 req/s peak with enormous headroom (single-instance throughput tests routinely exceed 100k ops/s). At 10× growth (5,000 req/s), a single Redis instance with consumer-group sharding still fits comfortably. If we later outgrow Redis Streams, the consumer-group abstraction makes the migration path to Kafka a producer-swap, not a full re-architecture.

## Consequences

### Pros

- **Immediate operability**: Redis is already in production. The team knows how to deploy, monitor, back up, and troubleshoot it. No new infrastructure to provision, learn, or staff for.
- **2-week delivery is realistic**: `XADD` / `XREADGROUP` / `XACK` are the only commands needed. A working async notification pipeline can ship in days, not weeks.
- **Consumer groups for free**: Redis Streams natively supports consumer groups with `XREADGROUP`, pending-entries lists for crash recovery (`XPENDING` / `XCLAIM`), and acknowledged processing (`XACK`). This gives us retry and at-least-once delivery out of the box.
- **Sufficient throughput**: At 500 req/s peak (each request producing 1–3 notification events), Redis Streams on existing hardware handles the load with >99% margin. The 10× growth target (5k req/s) remains well within single-instance capacity.
- **Dead-letter path**: Messages that exceed retry limits can be moved to a dead-letter stream (`DLQ-{original-stream}`), enabling operator inspection without blocking consumers.
- **WebSocket foundation**: The same Redis instance can serve as a pub/sub backbone for real-time push (Redis Pub/Sub or Streams), avoiding a second piece of infrastructure.
- **Cost**: No new infrastructure spend. The existing Redis instance (or a second dedicated instance at modest cost) covers it.

### Cons

- **No native exactly-once semantics**: Redis Streams provides at-least-once delivery. Exactly-once for billing notifications requires application-level idempotency (Postgres dedup table). This is an additional moving part, but it is also the correct architectural pattern — even Kafka's exactly-once semantics apply only within Kafka itself, not end-to-end across an external email provider.
- **Message retention is size/time-bounded**: Redis Streams uses `MAXLEN` or `MINID` trimming, not Kafka-style infinite retention with compaction. We must set a retention policy (e.g., `MAXLEN ~ 1,000,000` or `MINID ~ 7d`) and accept that very old messages are pruned. This is acceptable — notifications have a useful delivery window measured in hours, not weeks.
- **Memory-bound storage**: Redis holds streams in memory. At our volumes (~500 events/s × 86400 s/day × ~1 KB per event ≈ 1.2 GB/day untrimmed), memory is manageable with trimming but requires monitoring. Kafka's disk-based storage would not face this constraint.
- **No native partitioning across multiple Redis nodes**: Consumer groups distribute across consumers on a *single* stream, but there is no Kafka-style automatic partition rebalancing across a cluster. For our scale this is fine; at much higher volumes we would need Redis Cluster or a migration.
- **Operational risk of dual-purpose Redis**: Running both application cache (sessions, rate limiting) and message broker on the same instance creates contention risk under load. We mitigate this by provisioning a **dedicated Redis instance for streams** — still far cheaper than a Kafka cluster, and within our modest budget.
- **Migration effort if we outgrow it**: If traffic eventually exceeds Redis Streams' practical limits, migrating to Kafka is a real engineering effort (new infra, new operational runbooks, producer rewrite). The consumer-group abstraction limits the scope to the producer side, but it is not zero-cost.

## Alternatives Considered

### Apache Kafka — Rejected

Kafka is the stronger technical choice if assessed purely on streaming capabilities: higher max throughput, disk-based retention (no memory-pressure trade-offs), native partition-based parallelism, and exactly-once semantics via idempotent producers and transactional consumers.

However, it fails on every constraint that matters for this team at this time:

1. **No team experience**: Zero Kafka expertise means the first two weeks would be spent learning Kafka concepts (brokers, topics, partitions, consumer groups, offsets, compaction, replication factor), evaluating deployment options, and writing operational runbooks — before writing a single line of notification logic.
2. **Operational overhead**: A production Kafka cluster requires broker provisioning, ZooKeeper or KRaft configuration, replication factor tuning, partition strategy, monitoring (lag, under-replicated partitions, ISR shrink), and capacity planning. With no dedicated infra engineer, this falls on a team already maintaining a monolith.
3. **Managed Kafka cost**: AWS MSK or Confluent Cloud would reduce operational burden, but at our throughput scale (well under 10 MB/s), minimum-tier pricing significantly exceeds our budget. Self-hosted Kafka trades cost for operational toil that the team cannot absorb.
4. **Time-to-value**: The two-week constraint is the binding requirement. Kafka's setup, learning curve, and production hardening easily consume 2–4 weeks before the notification pipeline ships. Redis Streams can deliver a working pipeline in 3–5 days.
5. **Over-engineering for current scale**: Kafka's throughput advantage (hundreds of MB/s to GB/s) is orders of magnitude beyond our 10× growth target. We would pay the complexity cost for capacity we do not need.

**When to revisit**: If monthly active users exceed 500k, if we need multi-service event sourcing with long retention, or if we add a dedicated infrastructure engineer, Kafka becomes viable. The consumer-group abstraction in our Redis Streams implementation ensures the migration path is narrow and well-defined.