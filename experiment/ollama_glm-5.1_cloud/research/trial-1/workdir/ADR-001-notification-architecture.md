# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, peak ~500 req/s) handles notifications—emails and webhooks—synchronously inside the HTTP request cycle. This causes four concrete problems:

1. **Request timeouts**: Notification dispatch blocks responses. Average latency 800 ms, spiking to 8 s at peak.
2. **Silent failures**: Downstream email/webhook providers fail without retry or dead-letter capture.
3. **Cascading failures**: Slow webhook endpoints have exhausted the DB connection pool twice this year, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications (trial expiry, payment failure) must be delivered exactly once; the current system offers no such guarantee.

We must decouple notification from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), prepare for real-time WebSocket push within two quarters, and absorb 10× traffic growth without re-architecting.

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level); no dedicated infrastructure engineer.
- **Current stack**: Python/Flask monolith, PostgreSQL, Redis (sessions and rate limiting), 4 web servers on AWS.
- **Time**: Must deliver value within 2 weeks of starting migration.
- **Budget**: Modest; managed Confluent Cloud at production scale is not affordable today.
- **Experience**: No one on the team has operated Kafka. Redis is already in production.

## Decision

**We will use Redis Streams as the notification subsystem's message broker.**

Redis Streams satisfies our throughput requirements today and at 10× scale, provides the consumer-group and pending-entry primitives we need for reliable delivery, and can be deployed by a team that already operates Redis—within the 2-week window. Exactly-once semantics for billing notifications will be enforced at the application layer using idempotency keys backed by a PostgreSQL deduplication table.

## Consequences

### Pros

- **Fast time-to-value.** Redis is already in production. We add a stream data type and consumer-group logic—no new infrastructure to provision, monitor, or learn. First async notification can ship in days, not weeks.
- **Sufficient throughput.** A single Redis node handles 100K+ ops/sec. Our current peak (~500 req/s) and 10× target (~5K req/s) leave orders of magnitude of headroom. No sharding or partitioning required.
- **Consumer groups built in.** `XREADGROUP`, `XPENDING`, and `XCLAIM` give us partitioned consumption, automatic claim-transfer on worker failure, and visibility into pending messages—exactly the retry and failure-recovery primitives we need.
- **Configurable retention.** `MAXLEN` per stream caps memory. Time-based trimming (planned in Redis 8, available today via `MINID`) lets us keep unprocessed messages long enough for retries without unbounded growth.
- **Lower operational cost.** One fewer distributed system to run. No ZooKeeper/KRaft, no broker rack-awareness, no partition rebalancing. The team already knows Redis backup, replication, and alerting.
- **WebSocket-friendly.** Redis Pub/Sub (for fan-out) and Streams (for durable, ordered delivery) coexist in the same instance, simplifying the real-time push architecture planned for next quarter.

### Cons

- **No native exactly-once.** Redis Streams offers at-least-once. We achieve exactly-once for billing notifications by writing an idempotency key into each message and deduplicating in PostgreSQL before dispatch. This is application-level discipline, not a broker guarantee—and it must be coded correctly everywhere billing notifications are produced.
- **Memory-bound retention.** Streams live in RAM. Under sustained high throughput, `MAXLEN` must be set aggressively or memory usage grows. Long-term retention (months) is not practical; we must archive to PostgreSQL or S3 if audit trails are needed.
- **Single-node availability.** Redis Sentinel or Cluster is required for HA. We currently run a single Redis instance. Adding Sentinel is straightforward but must be planned before production traffic depends on the stream.
- **Weaker partition ordering.** Kafka orders within a partition; Redis orders within a stream. If we need per-entity ordering (e.g., all notifications for org 123 in sequence), we must use per-entity streams or append an entity key and reorder at the consumer. This is manageable at our scale but less elegant than Kafka's partition key routing.
- **Future migration ceiling.** If the platform grows past ~50K req/s or needs multi-data-center replication with strong consistency, Redis Streams will become a constraint, and a migration to Kafka will be required. That migration is not trivial—but it is also not needed at our current or 10× scale.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event platform. It excels at our requirements in theory:

| Property | Kafka | Redis Streams |
|---|---|---|
| **Throughput ceiling** | Millions of msgs/sec | ~100K+ ops/sec (single node) |
| **Ordering** | Per-partition, strict | Per-stream, strict |
| **Retention** | Disk-based, configurable to months/years | RAM-based, MAXLEN-trimmed |
| **Consumer groups** | Native, mature | Native, newer (XREADGROUP) |
| **Exactly-once** | Idempotent producers + transactions (native) | Not native; application-level dedup required |
| **Operational complexity** | High (brokers, partitions, KRaft/ZooKeeper) | Low (already running Redis) |
| **Team experience** | None | Already operating Redis daily |
| **Time to first value** | Weeks (cluster setup, topic design, client code, monitoring) | Days (add streams to existing Redis, write consumer) |

**Why we rejected Kafka for now:**

1. **Operational risk.** No one on the team has run Kafka. A misconfigured cluster under production load would cause the same kind of cascading failure we are trying to escape. The 2-week constraint makes responsible adoption impossible—we would still be learning broker tuning while the business waits for notification reliability.
2. **Cost.** Self-hosted Kafka requires dedicated brokers (minimum 3 for KRaft) plus monitoring (Prometheus exporters, JMX, Cruise Control). Managed Confluent Cloud at our projected ingest would exceed our infrastructure budget. Redis Streams adds zero incremental hosting cost.
3. **Premature scaling.** Our peak is ~500 req/s; 10× is ~5K req/s. Kafka's throughput advantage over Redis Streams only matters at scales an order of magnitude beyond our 10× target. We would pay the operational cost now for capacity we will not use for years.
4. **Migration path exists.** If throughput, retention, or multi-DC replication requirements eventually outgrow Redis Streams, we can migrate specific streams to Kafka using a dual-write or change-data-capture pattern. Rejecting Kafka today is not rejecting it forever—it is deferring it until the need is real.

**Revisit trigger:** Re-evaluate if sustained peak exceeds 20K req/s, if we need cross-region replication, or if the team hires a dedicated infrastructure engineer and can invest in Kafka operations.