# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

The notification module currently executes synchronously inside the Flask HTTP request cycle. This has caused request timeouts (avg 800ms, spikes to 8s), silent notification failures, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical events.

**Requirements:**
- Decouple notifications from HTTP request lifecycle (async processing)
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- WebSocket push notifications within 2 quarters
- Handle 10x traffic growth (500 → 5,000 req/s peak)

**Constraints:**
- Team: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience on the team
- Redis is already in production (session storage, rate limiting)
- Maximum 2-week setup/migration before delivering value
- Modest budget; Confluent Cloud at full scale is unaffordable today
- Exactly-once semantics required for billing notifications (trial expired, payment failed)

---

## Decision

**Choose Redis Streams as the notification subsystem message broker.**

Redis Streams is the correct choice given the team's size, the existing Redis footprint, the 2-week time-to-value constraint, and the absence of infrastructure engineering expertise. Kafka is rejected not because it is technically inferior for high-throughput, globally-ordered workloads, but because its operational complexity, steep learning curve, and cluster management burden would violate the team's constraints and timeline.

---

## Consequences

### Pros of Redis Streams

| Property | Detail |
|---|---|
| **Operational continuity** | Redis is already in production. No new infrastructure to provision, monitor, or secure beyond what the team already manages. |
| **Operational simplicity** | Single-node Redis Streams requires no cluster configuration, partition balancing, or replication tuning. The team uses existing Redis competence. |
| **Time to value** | A Redis Streams consumer group can be running in hours. Workers are plain Python threads or processes consuming via `XREADGROUP`. No schema registry, no topic configuration, no broker tuning. |
| **Throughput adequate for 10x growth** | At 500 req/s peak today (rising to ~5,000 req/s at 10x), Redis Streams handles 100,000+ msg/s on a single node comfortably. This is orders of magnitude above current and projected needs. |
| **Consumer groups (XREADGROUP)** | Native consumer group semantics provide load balancing across workers, per-message acknowledgment, and dead-letter queue via `XCLAIM` for messages that fail repeatedly. |
| **Existing Redis familiarity** | The team already manages Redis for sessions and rate limiting. Expertise transfers directly. |
| **Cost** | Uses existing infrastructure; no additional managed service spend. |
| **Ordered delivery per consumer group** | Messages within a consumer group are delivered in order, which is sufficient for per-user notification ordering. |

### Cons of Redis Streams

| Property | Detail |
|---|---|
| **No native exactly-once semantics** | Redis Streams provides at-least-once delivery only. Billing-critical notifications require application-level deduplication using a unique message ID stored in PostgreSQL or Redis as a dedup key. This is a well-understood pattern but adds implementation surface area. |
| **Memory-bound retention** | Streams consume heap memory proportional to message volume. Unacknowledged messages accumulate in the PEL (Pending Entries List). Requires `MAXLEN` trimming or `XTRIM` for high-volume streams, and monitoring of memory usage. Not an issue at current scale; must be watched at 10x. |
| **No native dead-letter queue** | Failed messages must be routed manually (e.g., a separate `notifications.dlq` stream) using `XCLAIM` after `XREADGROUP` returns a message that has been idle for a threshold. Requires custom retry logic. |
| **Horizontal scaling ceiling** | Scaling beyond a single Redis node requires Redis Cluster mode, which does not support Streams natively in the same way (Streams are sharded by key, not by stream). Operational complexity increases at this boundary. However, this ceiling is far above current and 10x-projected throughput. |
| **No native backpressure mechanism** | If workers are slower than producers, Redis memory grows. Workers must be autoscaled or producers must be throttled at the application layer. |
| **Fan-out for WebSocket push** | Supporting WebSocket push from Redis Streams requires a separate pub/sub subscription (`SUBSCRIBE`) or a separate stream per WebSocket session. The architecture must account for this in the 2-quarter WebSocket roadmap item. |

---

## Alternatives Considered

### Apache Kafka — Rejected

| Property | Kafka | Redis Streams |
|---|---|---|
| **Throughput** | Millions of msg/s (clustered) | 100,000+ msg/s (single node) |
| **Exactly-once semantics** | Native via Kafka transactions | Application-level via dedup key |
| **Ordering guarantees** | Per partition (global if keyed correctly) | Per consumer group |
| **Message retention** | Days to years, log-compacted | Memory-bound, configurable MAXLEN |
| **Consumer groups** | Mature, rich rebalancing semantics | Supported but simpler |
| **Operational complexity** | High — ZooKeeper/KRaft, partition assignment, replication tuning, broker monitoring | Low — Redis is already in production |
| **Learning curve** | Steep — no team experience | Minimal — existing Redis expertise |
| **Cluster management** | Required for HA and throughput | Single-node adequate for current + 10x scale |
| **Cost (self-hosted)** | 3+ brokers minimum for HA; compute + EBS costs | Marginal (uses existing Redis) |
| **Managed option** | Confluent Cloud (unaffordable at full scale) | Redis Cloud (scales with existing) |

**Why Kafka was rejected:**

1. **No team experience.** The 2-week constraint is incompatible with a team learning Kafka's mental model (topics, partitions, offsets, consumer groups, retention policies, replication) while simultaneously building a notification system.

2. **Operational burden.** A production-grade Kafka deployment on AWS (KRaft mode, 3+ brokers, replication factor 3, monitoring, alerting, log retention, partition rebalancing) requires an infrastructure engineer. The team of 6 has none.

3. **Cluster management overhead.** Adding brokers, rebalancing partitions, monitoring lag, and handling broker failures are routine ops tasks in Kafka that consume engineering time disproportionate to a 6-person team shipping a notification system.

4. **Exceedingly over-engineered for the problem.** At 5,000 req/s peak (the 10x target), Kafka is the right tool for millions of msg/s with strict global ordering and multi-consumer, multi-team workloads. Redis Streams is purpose-built for this team's actual scale.

5. **Exactly-once for billing is achievable with Redis Streams.** The exact-once requirement applies to billing notifications only. A dedup key written to PostgreSQL (already part of the billing record update) or a short-lived Redis SET with TTL is a straightforward, well-understood pattern. Kafka's exactly-once semantics are broader but also more expensive to operate.

6. **Migration path preserved.** If throughput or operational needs evolve beyond Redis Streams' practical ceiling, Kafka can be adopted with full team expertise at that time. Architectural decisions made under constraint are revisable when constraints lift.

---

## Summary

Redis Streams is the pragmatic choice. It leverages existing infrastructure, requires no new operational expertise, delivers value within the 2-week window, and provides sufficient throughput and reliability guarantees for the current problem and the 10x scaling target. Kafka's advantages (native exactly-once, million-msg/s throughput, global ordering) solve problems the team does not yet have, at a complexity cost the team cannot currently absorb.
