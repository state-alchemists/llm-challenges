# ADR-001: Notification Subsystem Architecture — Redis Streams

**Status:** Proposed

## Context

Our SaaS project-management platform (85K MAU, ~2M tasks/month, peak ~500 req/s) currently sends email and webhook notifications synchronously inside the Flask HTTP request cycle. This has caused:

- **Request timeouts**: average latency 800ms, spikes to 8s during peak hours.
- **Silent failures**: no retry or dead-letter queue when downstream providers fail.
- **Cascading failures**: slow webhook endpoints have exhausted connection pools and taken down unrelated features.
- **Missing delivery guarantees**: billing-critical notifications (e.g., "trial expired", "payment failed") can be dropped or duplicated.

We must decouple notification processing from the request cycle, add retry with exponential backoff, and guarantee at-least-once delivery for all events and exactly-once semantics for billing events. Within two quarters we also intend to support real-time WebSocket push notifications. The solution must accommodate 10× traffic growth (~5,000 req/s peak) without requiring another architecture migration.

**Constraints**

- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis is already in production (session storage and rate limiting).
- No Kafka operational experience on the team.
- Setup and migration must deliver value within 2 weeks.
- Budget is modest; managed Kafka (Confluent Cloud) at full scale is not viable today.

## Decision

**We will use Redis Streams as the backing message bus for the notification subsystem.**

While Apache Kafka is technically superior on raw throughput and native exactly-once semantics, Redis Streams is the better fit for our team size, existing expertise, budget, and two-week delivery window. The gap in exactly-once guarantees will be closed with application-level deduplication (idempotent consumers backed by a PostgreSQL deduplication table), which is sufficient for our current and 10× projected volumes.

### Technical Justification

| Property | Redis Streams (Chosen) | Apache Kafka (Rejected) |
|----------|------------------------|------------------------|
| **Operational complexity** | Low. We already run Redis for sessions and rate limiting. Monitoring, failover, and backup procedures are familiar. Adding Streams is a configuration change and client-code update, not a new operational domain. | High. Self-hosted Kafka requires cluster bootstrapping (KRaft or ZooKeeper), partition management, broker monitoring, and careful rebalancing. With no dedicated infrastructure engineer and zero prior experience, the risk of misconfiguration and on-call burden outweighs the benefits. |
| **Time to value** | Days. The existing Redis instance can accept stream writes immediately; consumer-group logic can be built and deployed within the two-week window. | Weeks to months just to build operational confidence. A 6-person team cannot safely self-host Kafka and ship the notification refactor in parallel within 14 days. |
| **Throughput** | A single Redis instance can sustain ~100K ops/sec. Our 10× target is ~5,000 req/s (notification events), leaving ample headroom. | Higher theoretical throughput, but we do not need it today or at 10× scale. |
| **Ordering guarantees** | Entries in a single Redis Stream are strictly ordered by auto-generated IDs. We will shard by notification category (e.g., `stream:billing`, `stream:general`) so ordering is preserved per topic. | Strong global ordering within a partition. Valuable, but unnecessary for our use case because billing events only need ordering relative to the same user/account, which we can enforce with stream sharding. |
| **Message retention** | Redis Streams support `MAXLEN` trimming. For notifications, we only need short-term retention (hours to days) to cover retry windows. Audit and compliance data will be archived to PostgreSQL, which we already operate. | Log-based, disk-persistent retention is cheaper and longer-term. Nice to have, but not worth the operational tax given our modest budget and short retry horizon. |
| **Consumer groups** | Native consumer groups with automatic message claiming and rebalancing are supported in Redis 5.0+. We can run multiple Flask worker processes as consumers without building custom coordination. | Mature consumer-group rebalancing with partition assignment. Superior at very large scale, but Redis Streams consumer groups are more than adequate for our volumes. |
| **Exactly-once semantics** | No native exactly-once delivery. **Mitigation**: we will implement idempotent consumers. Every billing event will carry a UUID generated at the producer. The consumer inserts processed UUIDs into a PostgreSQL `processed_events` table with a unique constraint. Duplicate deliveries are ignored. This pattern is well understood by the senior engineers on the team and satisfies the billing requirement. | Native exactly-once semantics (idempotent producer + transactions) are a genuine advantage. However, the operational cost of self-hosting Kafka to obtain this feature is disproportionate for a team of our size. |
| **Infrastructure cost** | Zero additional infrastructure. Uses the existing Redis instance (or a small vertically scaled instance if needed). | Requires additional EC2 instances (or equivalent) for brokers, storage, and KRaft controllers. Exceeds our modest budget for this phase. |

## Consequences

### Pros

1. **Rapid delivery**: We can begin moving notifications off the HTTP request cycle within days, directly addressing the timeout and cascading-failure problems.
2. **Low operational risk**: The team already operates Redis. On-call playbooks, monitoring dashboards, and backup strategies do not need to be invented from scratch.
3. **Cost efficiency**: No new managed service or additional server fleet is required.
4. **Path to WebSocket push**: Redis Pub/Sub (or a secondary consumer on the same Streams) can be introduced in the next quarter for real-time WebSocket delivery without adding a third messaging system.
5. **Sufficient headroom**: 5,000 events/sec at peak is well within single-instance Redis capabilities, giving us runway before a more complex architecture becomes necessary.

### Cons

1. **Memory-bound retention**: Redis is an in-memory store. If trimming is misconfigured or growth exceeds memory capacity, we could lose unprocessed messages. **Mitigation**: aggressive `MAXLEN` policies, memory alarms, and continuous archiving of billing events to PostgreSQL.
2. **Application-level exactly-once burden**: We must build and maintain the deduplication table and idempotent consumer logic. Bugs here could lead to duplicate billing notifications.
3. **Shared fate with sessions/rate limiting**: A Redis outage now affects authentication and notifications simultaneously. **Mitigation**: we will evaluate Redis Sentinel or a small HA pair (already a planned infra improvement) to reduce downtime.
4. **Weaker stream-processing ecosystem**: No Kafka Connect equivalent for easily integrating third-party sinks. We will write small Python consumers instead, which is acceptable for our limited integration surface.
5. **Harder long-term scaling**: If we eventually outgrow Redis Streams (e.g., >50K events/sec, multi-region replication, complex stream joins), we will likely need to migrate to Kafka or a managed event service. We accept this future replanning risk because it is years away at current growth rates.

## Alternatives Considered

### Apache Kafka

Kafka was the primary alternative. It offers best-in-class durability, native exactly-once semantics, cheap disk-based retention, and a mature ecosystem (Kafka Connect, schema registries). These properties make it the industry-standard choice for high-volume event streaming.

We rejected it because:

- **Operational burden**: Self-hosting Kafka safely requires expertise our team does not have. Without a dedicated infrastructure engineer, the risk of operational incidents (e.g., partition leader imbalances, broker failures, consumer lag storms) is unacceptably high.
- **Timeline mismatch**: Building production-grade Kafka expertise, standing up a cluster, and migrating the notification pipeline cannot be done in two weeks without sacrificing quality or other roadmap commitments.
- **Budget constraints**: Managed Kafka (Confluent Cloud, AWS MSK at scale) is outside our budget. Self-hosted Kafka still incurs new EC2 and storage costs.
- **Over-engineering for current needs**: Our throughput requirements (even at 10×) are modest. Kafka’s advantages become decisive at tens or hundreds of thousands of events per second, not at 5,000 req/s.

If the team doubles in size, hires infrastructure expertise, and throughput crosses a threshold where Redis becomes a bottleneck, we will revisit Kafka. For the next 12–24 months, Redis Streams is the right trade-off.
