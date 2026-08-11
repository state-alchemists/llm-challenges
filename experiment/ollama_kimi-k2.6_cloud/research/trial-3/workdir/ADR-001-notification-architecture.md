# ADR-001: Notification Subsystem Architecture — Redis Streams

## Status

**Proposed**

## Context

Our SaaS project management platform currently sends emails and webhooks synchronously inside the Python/Flask HTTP request cycle. At our current scale (~85,000 MAU, peak ~500 req/s, ~2M tasks/month), this has become untenable:

- **Request timeouts** block users for an average of 800ms, spiking to 8s during peak hours.
- **Silent failures** occur when downstream email providers or webhook endpoints are down; there is no retry mechanism or dead-letter queue.
- **Cascading failures** have caused two outages this year when a slow webhook endpoint exhausted the database connection pool, taking down unrelated features.
- **No delivery guarantees** exist for billing-critical notifications (e.g., "trial expired", "payment failed"), which must be delivered at least once and ideally exactly once.

Our scaling targets require us to decouple notifications from the HTTP request cycle, support retry with exponential backoff, guarantee delivery for billing events, add real-time WebSocket push notifications within two quarters, and handle 10x traffic growth without re-architecting.

We face significant constraints:

- **Team size:** 6 engineers (3 senior, 3 mid-level), with **no dedicated infrastructure engineer**.
- **Existing infrastructure:** Redis is already in production (session storage, rate limiting).
- **Experience:** **No Kafka experience** on the team.
- **Timeline:** Must deliver value within **2 weeks** of setup/migration work.
- **Budget:** Modest; we cannot afford managed Confluent Cloud at full scale today.
- **Requirement:** Must maintain exactly-once semantics for billing notifications.

We evaluated two options for the new notification backbone: **Apache Kafka** and **Redis Streams**.

## Decision

We will adopt **Redis Streams** as the notification subsystem's event backbone.

### Justification

Given our team size, timeline, budget, and existing infrastructure, Redis Streams provides the best risk-adjusted path to meeting our functional and scaling requirements. While Apache Kafka offers stronger native exactly-once semantics and theoretically unlimited horizontal scaling, its operational complexity exceeds what a 6-person team with no Kafka experience can safely manage within a two-week window.

Key technical factors:

| Property | Redis Streams | Apache Kafka |
|----------|---------------|--------------|
| **Throughput** | >100k messages/sec per node (single-threaded event loop). At our peak of ~500 req/s and even 10x growth, this is ample headroom. | Millions of messages/sec across a cluster. Massive overkill for our current scale. |
| **Ordering guarantees** | Total ordering within a single stream. We can shard by notification type or tenant to maintain per-user ordering where required. | Strong per-partition ordering. Requires careful partition key design to avoid hotspots. |
| **Message retention** | Configurable (`XTRIM` by maxlen or age), but **memory-bound**. We will mitigate by trimming aggressively and archiving dead-letter events to PostgreSQL or S3. | Disk-based retention (time or size), effectively unbounded. Native log compaction. |
| **Consumer groups** | Supported via `XREADGROUP` with explicit ACKs (`XACK`). Mature enough for our worker pool model. | Mature consumer group rebalancing, offset management, and partition assignment. |
| **Exactly-once semantics** | **Not native**. Redis Streams provides at-least-once delivery. Exactly-once must be enforced at the application layer via idempotent consumers. | Native exactly-once via idempotent producers + transactions + isolation levels. |
| **Operational complexity** | **Low**. We already operate Redis. Adding Streams is a configuration change, not a new distributed system. | **High**. Requires broker tuning, KRaft/ZooKeeper management, partition rebalancing, and deep operational expertise we do not have. |
| **Time to production** | **Days**. Can reuse existing Redis or spin up a new Redis instance with persistence enabled. | **Weeks to months** for a safe self-managed deployment by an inexperienced team. |
| **Infrastructure cost** | **Minimal**. No new managed service; Redis is already budgeted. | **Significant**. Self-hosted Kafka on AWS requires dedicated EC2 instances or MSK. Managed offerings (Confluent, MSK) exceed our modest budget at scale. |

#### Exactly-Once Strategy for Billing Notifications

The primary risk of Redis Streams is the lack of native exactly-once delivery. We will mitigate this with **application-level idempotency**:

1. **Idempotent producers:** Each notification event will carry a deterministic UUID (e.g., `SHA256(tenant_id + event_type + entity_id + timestamp_bucket)`).
2. **Deduplication on consume:** Before processing a billing notification, the consumer will insert the event UUID into a PostgreSQL table with a `UNIQUE` constraint. A duplicate UUID will trigger a constraint violation, and the event will be ACKed without re-processing.
3. **Transactional outbox pattern (where needed):** For the most critical billing events, we will write the event to an outbox table in PostgreSQL within the same transaction as the business logic, then have a relay process publish to Redis Streams. This prevents publishing without persisting.

This approach is well-documented, adds minimal latency, and is straightforward for our senior engineers to implement correctly. It shifts complexity from infrastructure operations to application logic—a favorable trade-off given our constraints.

## Consequences

### Pros

- **Fast time to value:** We can begin decoupling notifications from the HTTP cycle within days, well under the 2-week mandate.
- **Low operational overhead:** The team already understands Redis backup, monitoring, and failover. We are not taking on a new distributed system.
- **Sufficient throughput and ordering:** Redis Streams can handle our current and projected 10x load with total ordering per stream, satisfying our near-term needs.
- **Zero additional licensing or infrastructure cost:** We reuse existing Redis capacity or provision a modest new Redis instance—orders of magnitude cheaper than standing up a Kafka cluster.
- **Future WebSocket synergy:** Redis Pub/Sub (or dedicated Streams consumers) provides a natural path to the real-time push notifications planned for the next two quarters.
- **Consumer group scaling:** Python worker processes can horizontally scale reads via `XREADGROUP`, and failed workers will have their pending messages claimed by others after a timeout (`XPENDING` + `XCLAIM`).

### Cons

- **Memory-bound retention:** Message retention is constrained by available RAM. Aggressive trimming and archiving to PostgreSQL/S3 are required to prevent eviction. With 10x growth, we may need to evaluate Redis Cluster or a dedicated stream node.
- **Exactly-once requires application discipline:** We lose the safety net of broker-level exactly-once semantics. A bug in our idempotency logic could lead to duplicate billing notifications.
- **Persistence configuration gap:** Our current Redis instance may be configured for cache-style ephemeral use (RDB snapshots only or no AOF). We must evaluate and likely enable AOF (`appendfsync everysec`) to prevent unacknowledged message loss on restart.
- **Single-node bottleneck:** A single Redis primary can become a hotspot. While our scale is manageable today, we must monitor CPU/memory and plan for Redis Cluster or a separate high-availability Redis deployment as we approach 10x scale.

## Alternatives Considered

### Apache Kafka — Rejected

We rejected Apache Kafka because its operational burden is incompatible with our team constraints and timeline, despite its architectural superiority for large-scale stream processing.

**Why it was appealing:**
- Native exactly-once semantics (idempotent producers, transactional consumes) would eliminate the need for application-level deduplication.
- Disk-based retention and log compaction are ideal for audit trails and replay.
- Partitioning model scales linearly to millions of events per second, offering a true "never re-architect" promise.

**Why it was rejected:**
- **Operational complexity:** Running a self-managed Kafka cluster (KRaft or ZooKeeper, broker tuning, replication factors, partition rebalancing, monitoring) requires expertise we do not have and cannot safely acquire in two weeks without a dedicated infrastructure engineer.
- **Experience gap:** Our team has zero production Kafka experience. Misconfiguring `acks`, `retries`, `enable.idempotence`, or transactional consumer isolation levels would silently undermine the exactly-once guarantees we need.
- **Time to value:** A production-ready, monitored, and tested Kafka deployment—including client library integration, producer/consumer error handling, and operational runbooks—would realistically take 4–8 weeks for this team.
- **Cost:** Self-hosted Kafka requires additional EC2 instances or MSK spend. Managed Confluent Cloud is explicitly ruled out by budget constraints at our projected scale.
- **Over-engineering:** Our throughput needs (even at 10x) are comfortably within the bounds of a well-configured Redis instance. Kafka solves a problem we do not yet have at the cost of creating immediate operational risk.

If we exceed the throughput or retention limits of Redis Streams in the future, we can revisit Kafka. By then, we will have async infrastructure in place (idempotent consumers, outbox patterns, monitoring) that will make a future Kafka migration far lower risk than attempting it today under time pressure.
