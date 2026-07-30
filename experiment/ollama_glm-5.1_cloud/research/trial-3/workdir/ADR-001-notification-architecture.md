# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, ~500 req/s peak) handles all notification delivery — emails, webhooks, and future WebSocket push — synchronously inside the HTTP request cycle. This has caused three operational incidents this year: request timeouts (800ms avg, 8s spikes), silent notification drops with no retry or dead-letter queue, and cascading failures from slow webhook endpoints exhausting the database connection pool. Billing-critical notifications ("trial expired", "payment failed") have no delivery guarantees today.

We need to decouple notification processing from the request path, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), support real-time WebSocket push within 2 quarters, and handle 10x traffic growth (~5,000 req/s) without re-architecting.

Constraints shaping this decision:

- **6-person engineering team** (3 senior, 3 mid-level), no dedicated infrastructure engineer
- **Redis already in production** for sessions and rate limiting
- **No Kafka experience** on the team
- **2-week maximum** before the migration delivers user-facing value
- **Modest budget** — managed Confluent Cloud at production scale is not affordable
- **Exactly-once semantics required** for billing notifications

## Decision

**We choose Redis Streams.**

Redis Streams provides consumer-group semantics (`XREADGROUP`), persistent append-only logs with configurable retention, pending-entry-lists for retry and dead-letter handling, and operates at throughput levels well beyond our 10x scaling target — all on infrastructure we already run and a data model the team can learn in days, not weeks.

The exactly-once requirement for billing notifications will be satisfied through **application-level idempotency**: each billing event carries a deterministic deduplication key (e.g., `billing:{org_id}:{event_type}:{period}`), and consumers record processed keys in a Redis SET with TTL before acting. This is the standard pattern for exactly-once-over-at-least-once, avoids the operational overhead of Kafka's transactional protocol, and is auditable in PostgreSQL where billing state already lives.

Kafka is the stronger choice at extreme scale and offers native exactly-once delivery via transactional producers — but those advantages do not outweigh the operational and time-to-value costs for our team and timeline.

## Consequences

### Pros

- **Immediate time-to-value.** Redis is already in production; Streams require no new infrastructure. Consumer-group-based workers can ship within the 2-week window, immediately removing notification logic from the HTTP path and eliminating the timeout and cascading-failure incidents.
- **Low operational burden.** No new distributed system to deploy, monitor, or scale. The team's existing Redis operational knowledge (AOF persistence, replication, alerting) transfers directly. No ZooKeeper/KRaft, no broker rebalances, no partition assignment to tune.
- **Sufficient throughput and growth headroom.** Redis Streams handle 100K+ operations/second on a single node. Our 10x target (~5,000 req/s sustained, accounting for burst multiplicity) sits well below that ceiling. Horizontal scaling via Redis Cluster is available if we exceed single-node capacity later.
- **Native consumer groups.** `XREADGROUP` provides partition-free parallel consumption with automatic pending-entry tracking (`XPENDING`/`XCLAIM`), giving us retry, redelivery, and dead-letter semantics without custom coordination logic.
- **WebSocket integration path.** Redis Pub/Sub (already available) or consumer groups on a dedicated `notifications:push` stream can fan out real-time updates to WebSocket gateway processes — no additional message broker required.
- **Cost-neutral.** No new infrastructure spend. The existing Redis instance (or cluster) absorbs notification traffic alongside sessions and rate limiting.

### Cons

- **Exactly-once is application-level, not broker-level.** Redis Streams provide at-least-once delivery. We achieve exactly-once for billing events through idempotency keys and processed-event tracking in Redis/PostgreSQL. This is correct and auditable but requires discipline in the consumer code — every billing handler must check-and-set the dedup key before acting.
- **Retention is time- or count-bounded, not infinite.** Redis Streams are trimmed by `MAXLEN` or `MINID`. This is appropriate for notifications (current business value is recent), but Kafka's configurable long-term retention is more suitable if we later need months of event replay. Mitigation: archive consumed events to PostgreSQL or S3 for long-term audit before trimming.
- **No native compaction by key.** Kafka log compaction retains the latest value per key automatically. Redis Streams lack this. If we need compacted state (e.g., last-known status per task), we must maintain it separately — a Redis Hash or PostgreSQL table.
- **Single Redis node is a SPOD.** Without Redis Cluster, a node failure stops notification processing. Mitigation: enable Redis replication with automatic failover (Redis Sentinel), which the team can configure on existing infrastructure. At our scale, a Sentinel-backed primary-replica pair is sufficient through the 10x growth target.
- **Less ecosystem tooling.** Kafka has richer connectors, schema registries, and monitoring (Burrow, Kafka Manager). For our use case — a single-service notification pipeline — this is unnecessary overhead. If the platform later needs multi-service event routing or a central event bus, Redis Streams will show its limits and a migration to Kafka should be reconsidered at that point.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming. Its advantages over Redis Streams are real:

| Property | Kafka | Redis Streams |
|---|---|---|
| Throughput | Millions of msgs/s across partitions | ~100K+ ops/s single node |
| Ordering | Per-partition strict | Per-stream strict (no partitions needed) |
| Retention | Configurable (time or size), infinite possible | `MAXLEN` or `MINID` trimming |
| Consumer groups | Native, with partition rebalancing | Native via `XREADGROUP`, simpler model |
| Exactly-once | Broker-level via transactional producers | Application-level idempotency required |
| Log compaction | Native | Not supported |
| Operational complexity | High (brokers, ZooKeeper/KRaft, partition management) | Low (feature on existing Redis instance) |

**Why we rejected Kafka for this decision:**

1. **Operational cost exceeds our capacity.** A production Kafka deployment requires at least 3 brokers for replication, plus ZooKeeper or KRaft controllers. Our 6-person team has no Kafka experience and no dedicated infrastructure engineer. Operating Kafka correctly — handling rebalances, monitoring lag, tuning partitions, managing schema evolution — demands expertise we would have to build from zero.

2. **Time-to-value is too long.** Kafka setup, team training, and a production-hardened deployment would take 4–8 weeks minimum, violating the 2-week constraint. Redis Streams lets us ship working async notification processing within the deadline.

3. **Managed Kafka is not budget-feasible.** Confluent Cloud or AWS MSK at our target scale would cost $500–$1,500+/month. Redis Streams add $0 to our current Redis spend.

4. **Our scale doesn't require Kafka yet.** At ~500 req/s peak (target: 5,000 req/s), we are orders of magnitude below Kafka's design ceiling. Redis Streams handles this volume comfortably. Premature adoption of Kafka introduces operational complexity with no throughput benefit.

Kafka should be reconsidered if and when we outgrow Redis Streams — specifically, if we need multi-service event routing, long-term event replay, or throughput beyond Redis Cluster capacity. At that point, the team will have grown and accumulated the operational maturity to run it safely.