# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

Our Flask monolith handles notifications synchronously inside the HTTP request cycle, causing request timeouts (avg 800ms, spikes to 8s), silent failures on downstream errors, cascading failures from slow webhook endpoints, and zero delivery guarantees for billing-critical events. We need to decouple notification processing, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), and absorb 10x traffic growth without re-architecting.

**System constraints:**
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience on the team
- Redis is already in production (sessions, rate limiting)
- 2-week maximum setup/migration window before delivering value
- Modest budget — cannot afford managed Confluent Cloud at full scale
- Must maintain exactly-once semantics for billing notifications
- Current load: ~2M tasks/month, peak ~500 req/s (notifications will be a fraction of this)

## Decision

**Chosen option: Redis Streams**

Redis Streams is the correct choice given our constraints. It delivers async message processing immediately with our existing infrastructure, allows the team to ship value within days rather than weeks, and provides sufficient throughput for our current and 10x-scaled workload.

### Technical Justification

**Throughput:** At 500 req/s peak with notification events being a subset of requests, we are orders of magnitude below Redis Streams' capacity. A single Redis node handles 100k–500k events/second; even with aggressive buffering and 10x growth, we will not approach those limits. Kafka's raw throughput advantage is irrelevant at our scale.

**Ordering guarantees:** Both Kafka (per-partition) and Redis Streams (per-stream) provide strong ordering guarantees. For notification workloads — task created → notification sent — ordering within a stream is sufficient. We will use one stream per notification type (e.g., `notifications:email`, `notifications:webhook`), which naturally scopes ordering to the right granularity.

**Consumer groups:** Redis Streams' `XREADGROUP` provides consumer group semantics equivalent to Kafka consumer groups: multiple workers can share load, track individual progress with `XPENDING`, and redeliver unacknowledged messages. The mental model maps directly.

**Message retention:** Redis Streams supports configurable length limits (`MAXLEN`) and approximate trimming, which is sufficient for our use case — notifications are processed immediately or retried, not consumed retroactively by multiple downstream systems. Kafka's infinite retention with compaction is overkill for an notification workload where messages have a finite processing window.

**Exactly-once semantics:** Neither Kafka nor Redis Streams provides application-level exactly-once delivery out of the box without idempotency logic. Kafka's exactly-once semantics (`transactional.id`) requires broker-side configuration and consumer-side commits, adding complexity. For billing notifications, we will implement deduplication at the application layer using a `billing_notifications` table in PostgreSQL with a unique event ID, which is straightforward and does not require Kafka transactions. This pattern works identically with Redis Streams and is already an established pattern in our codebase.

**Operational complexity:** This is the decisive factor. Redis Streams requires zero new infrastructure — it runs on our existing Redis instance (or a trivially added replica). There is no cluster sizing, no partition strategy, no ZooKeeper/KRaft setup, no broker monitoring. The team already knows Redis. Kafka, by contrast, requires learning broker configuration, replication factor, partition count, consumer group offset management, and retention tuning — knowledge that does not exist on the team today and cannot be acquired within the 2-week constraint.

**Delivery guarantees:** Redis Streams with `XACK` and `XPENDING` provides at-least-once delivery. Workers acknowledge only after successful processing; unacknowledged messages are redelivered by other consumers after the `BLOCK` timeout. This is sufficient for all notification types, with billing deduplication handled at the application layer.

## Consequences

### Pros of Redis Streams

- **Zero new infrastructure:** Runs on existing Redis; no new servers, no new services to monitor
- **Fastest path to value:** The team can implement a working producer/consumer within days using familiar Redis clients (`redis-py`, `ioredis`). No Kafka library knowledge required.
- **Consumer groups are a first-class feature:** `XREADGROUP`, `XACK`, `XPENDING` cover the full "at-least-once with retry" pattern natively
- **Existing expertise:** All 6 engineers already understand Redis; the learning surface is minimal
- **Retry with exponential backoff:** Implementable in the consumer worker using `XPENDING` visibility timeout and redelivery; or via a simple polling loop with a backoff multiplier
- **Dead-letter queue:** Achieved by maintaining a separate stream `notifications:dlq` and routing messages that exceed a retry threshold — no additional infrastructure
- **WebSocket push support (near-term):** Redis pub/sub (`SUBSCRIBE`) can be used for real-time push to WebSocket clients within the same Redis instance, aligning with the 2-quarter WebSocket roadmap without adding a second system
- **Cost:** No additional AWS spend beyond potential Redis memory allocation; no licensing costs

### Cons of Redis Streams

- **No native exactly-once:** Application-level deduplication required for billing events. This is a minor implementation cost — a PostgreSQL table with a unique event ID column and an `INSERT ... ON CONFLICT DO NOTHING` query. This pattern is well-understood and not novel.
- **Horizontal scalability ceiling:** A single Redis Streams consumer group can saturate one CPU core. Scaling beyond that requires multiple consumer groups or sharding. At our current and 10x-scaled throughput (sub-10k notifications/sec even with generous buffering), this is not a constraint in practice.
- **Memory-bound retention:** If consumer lag grows significantly, messages held in the stream consume RAM. With `MAXLEN ~` approximate trimming and a properly sized stream window (minutes to low hours), this is manageable. Kafka's disk-backed storage does not have this concern at scale.
- **No宽限期 (no built-in "catch-up" for new consumers):** New consumer group instances start reading from the current head of the stream, not from the earliest unprocessed message, unless `COUNT` is used with `$` semantics. This requires careful consumer group initialization on first deploy.
- **Operational visibility:** Kafka's rich ecosystem (Confluent Control Center, Kafka Manager, etc.) provides deeper observability into consumer lag and throughput. Redis Streams monitoring requires `MONITOR`, `XINFO`, and custom metrics — less mature tooling, but sufficient with standard Redis metrics and basic consumer-side instrumentation.
- **Multi-dc/hybrid deployment:** Running Redis Streams across availability zones requires Redis Cluster or replication. If the team expands to multi-region, Kafka's cross-dc replication is more battle-tested. This is not a current requirement.

## Alternatives Considered

### Apache Kafka

Kafka's strengths — infinite retention, disk-backed scalability, mature exactly-once semantics, and a rich ecosystem — are real, but they are designed for problems we do not have.

- **Operational burden is disproportionate to our scale.** A minimal production-ready Kafka deployment requires at minimum 3 brokers with replication factor 3, ZooKeeper or KRaft configuration, topic/partition strategy, and consumer group offset management. For a team of 6 with no Kafka experience and a 2-week constraint, this is not feasible to ship safely.
- **No existing infrastructure.** Kafka would require new AWS resources (MSK or self-managed EC2), new monitoring (JMX metrics, consumer lag alerts), new operational runbooks, and new deployment pipelines. Redis Streams requires a single configuration change to an existing Redis instance.
- **The learning curve is a project risk.** The team would need to learn producer/consumer APIs, partition strategies, consumer group offset management, and exactly-once configuration concurrently while building the notification system. With no prior Kafka experience, discovery and correction of misunderstandings will eat the 2-week window.
- **Managed Kafka (Confluent Cloud) is budget-prohibitive at scale.** Self-managed Kafka on EC2 introduces the operational complexity above at the cost of infrastructure spend that the budget cannot absorb today.

Kafka would be the correct choice if: the team had a dedicated platform/infrastructure engineer, the system needed cross-service event streaming for multiple consumers beyond notifications, or the throughput requirement was 100k+ events/second sustained. None of those conditions apply.

### Rejected: Keep Synchronous Processing

This option was rejected in the problem statement. It causes the four known failure modes: request timeouts, silent failures, cascading failures, and zero delivery guarantees. It is not viable.

### Rejected: Database Polling (e.g., a `notifications` table + scheduled job)

Polling a database table for new rows is operationally simple but introduces polling latency, does not support push-based retry, creates contention on the database, and does not scale. It is a step backward from the current system in every dimension that matters for a SaaS platform with growth targets.

---

## Summary

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| Throughput | 100k–500k/s (single node) | Millions/s (cluster) |
| Ordering | Per-stream | Per-partition |
| At-least-once | Native (`XACK`) | Native |
| Exactly-once | Application-level dedup | Native (transactions, complex) |
| New infrastructure | None | Yes (brokers, ZooKeeper/KRaft) |
| Team learning curve | Minimal (already know Redis) | Steep (no Kafka experience) |
| Time to first value | Days | 2+ weeks minimum |
| Message retention | Memory-bounded (`MAXLEN`) | Disk-backed, configurable |
| Consumer groups | Native (`XREADGROUP`) | Native |
| Operational complexity | Low | High |
| Budget impact | Minimal | Significant (infra + managed service if needed) |

**Recommendation: Implement the notification subsystem using Redis Streams.** Application-level deduplication via a PostgreSQL `billing_notifications` table with unique event IDs provides exactly-once semantics for billing events. This is the fastest, lowest-risk path to solving the four known failure modes within the 2-week constraint while leaving headroom for 10x growth.
