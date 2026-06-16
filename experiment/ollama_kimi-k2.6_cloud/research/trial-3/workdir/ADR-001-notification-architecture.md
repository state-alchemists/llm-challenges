# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project-management platform (85,000 MAU, ~2M tasks/month, peak 500 req/s) currently sends email and webhook notifications synchronously inside the Flask HTTP request cycle. This has produced:

- **Request timeouts** – average 800 ms, spikes to 8 s during business hours.
- **Silent failures** – dropped notifications when downstream providers are down; no retry or dead-letter mechanism exists.
- **Cascading failures** – two incidents this year where a slow webhook exhausted the DB connection pool and degraded unrelated features.
- **No delivery guarantees** – billing-critical events ("trial expired", "payment failed") must be delivered exactly once, yet duplicates and drops are both possible today.

We must decouple notification dispatch from the request cycle, add retry with exponential backoff, and lay groundwork for real-time WebSocket push within two quarters. The target is 10× traffic growth without re-architecting.

**Team & operational constraints**
- Engineering team: 6 people (3 senior, 3 mid-level); no dedicated infrastructure engineer.
- Redis is already in production (sessions, rate limiting).
- No prior Kafka experience.
- Migration must deliver value within **two weeks**.
- Budget is modest; fully-managed Confluent Cloud is not affordable at target scale today.

The two candidate streaming substrates are **Apache Kafka** and **Redis Streams**.

## Decision

We will adopt **Apache Kafka** as the backbone of the notification subsystem.

### Justification

| Property | Apache Kafka | Redis Streams |
|----------|--------------|---------------|
| **Throughput & horizontal scale** | Partition-based scale-out; producers and consumers are independent. Proven to absorb 10× our peak (5,000 req/s) with modest broker counts. | Single-stream command-processing limits headroom; hot-key contention appears earlier under sustained write load. |
| **Ordering guarantees** | Strict per-partition total order; immutable log segments prevent in-place corruption. | Per-stream ordering, but TTL/eviction and memory pressure can drop messages silently before consumers read them. |
| **Message retention** | Disk-backed, configurable retention (days–weeks). Billing audit trails can be retained cheaply. | Memory-first with optional AOF/RDB snapshots. Retaining millions of billing events for replay risks OOM or forced eviction. |
| **Consumer groups** | Mature rebalance protocol, graceful partition migration on consumer join/leave, and committed-offset recovery. | Simpler consumer-group model; stalled-consumer detection and rebalancing are coarser and can leave partitions idle during recovery. |
| **Exactly-once semantics** | Native EOS: idempotent producers (`enable.idempotence=true`) plus transactions (`producer.init_transactions` / `send_offsets_to_transaction`). Gives us the exactly-once guarantee required for billing notifications without bespoke application code. | At-least-once only. Exactly-once would require building our own deduplication layer (e.g., PostgreSQL UPSERT of processed UUIDs) inside every consumer, increasing correctness risk for a team with no streaming infrastructure experience. |
| **Operational complexity** | Higher upfront: broker tuning, partition planning, and monitoring (JMX, lag metrics). Mitigated by starting with a minimal 3-node KRaft cluster (no ZooKeeper) or low-tier AWS MSK. | Lower upfront because Redis already runs, but the *notification* workload is different from cache workloads—memory sizing, persistence tuning, and eviction policies must be re-validated. |

**Why Kafka wins given our constraints**
1. **Exactly-once is non-negotiable for billing.** Kafka is the only option of the two that provides this guarantee natively across producers and consumers. Building it ourselves on Redis Streams would require distributed deduplication logic that a 6-person team cannot safely operate without dedicated streaming expertise—precisely the expertise we lack.
2. **10× growth without re-architecting.** Kafka’s log-centric design is deliberately built for magnitude-scale growth. Choosing Redis Streams today defers complexity but creates a hard ceiling on retention and throughput that will force a painful migration within 12–18 months.
3. **Two-week delivery is achievable for an MVP topic.** We will scope the initial rollout to a single `billing.notifications` topic with one partition, a minimal replicated broker set, and a small Python consumer group using `confluent-kafka`. This does not require Confluent Cloud; AWS MSK Serverless or a small KRaft cluster meets the modest budget.
4. **Future WebSocket push.** Kafka’s durable replay log lets us add a new consumer group for WebSocket broadcast later without touching producers, satisfying the two-quarter roadmap item.

## Consequences

### Positive
- **Durability guarantees** eliminate silent notification drops; billing events are protected by Kafka’s replicated commit log.
- **Exactly-once processing** removes the need for custom deduplication logic, shrinking the correctness surface area.
- **Independent consumer scaling** means retry workers, real-time push, and analytics can each consume the same event stream at their own pace.
- **Horizontal growth path** supports the 10× target without structural changes.

### Negative
- **Learning curve.** The team must ramp up on partitioning strategies, consumer lag monitoring, and broker maintenance. We will allocate senior-engineer pairing time and run a tabletop failover drill in week 3.
- **Upfront infrastructure work.** Even a minimal cluster requires provisioning, monitoring, and run-book creation during the two-week sprint. We will de-scope non-critical notification types to week 4 to protect the deadline.
- **Cost.** Three broker instances (or low-tier MSK) add continuous compute cost versus re-using existing Redis capacity. This is accepted because the cost of a missed "payment failed" notification (churn, support burden, compliance risk) exceeds the infrastructure spend.
- **Tooling gap.** We currently lack Kafka dashboards and alerting. We must stand up lag exporters (e.g., Prometheus + Kafka Exporter) immediately alongside the cluster.

## Alternatives Considered

### Redis Streams

Redis Streams was attractive because Redis is already deployed and the team knows it. A prototype could be wired into Flask in days.

It was rejected because:
- **No native exactly-once semantics.** The billing-critical requirement would push correctness complexity into application code, where mistakes are likely given our team size and lack of streaming experience.
- **Memory-bound retention.** Retaining a growing log of billing events for replay, audit, and new-consumer catch-up contradicts Redis’s cache-optimized design; we would eventually need to archive to S3 or another store, re-creating Kafka’s log functionality poorly.
- **Coarse consumer-group behavior.** Partition rebalancing and failure recovery are less granular than Kafka’s, which increases the risk of duplicate or stalled processing during deploys or instance failures.

Redis will remain in its current roles (sessions, rate limiting). It is not removed from the architecture; it is simply judged unsuitable as the primary event log for a mission-critical notification pipeline.
