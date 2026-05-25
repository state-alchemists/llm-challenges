# ADR 001 — Notification Subsystem: Async Decoupling with Redis Streams

- **Status**: Proposed
- **Date**: 2026-05-25
- **Deciders**: Engineering Team
- **Context tags**: notifications, async-processing, messaging, redis, kafka

## Context

The project management platform sends email and webhook notifications when tasks are updated, assigned, or completed. These notifications are sent synchronously within the HTTP request cycle, causing average response latencies of 800 ms with spikes to 8 seconds during peak hours. Two production incidents this year resulted from slow webhook endpoints exhausting the PostgreSQL connection pool, cascading into unrelated features. Billing-critical notifications (trial expiry, payment failure) have no delivery guarantees and are silently dropped on provider failure.

The system must be decoupled to move notification delivery out of the request path. Key requirements: at-least-once delivery for all events, exactly-once semantics for billing events, retry with exponential backoff, dead-letter queue for poison messages, and a path to real-time WebSocket push within two quarters. The solution must handle 10x traffic growth from the current peak of ~500 req/s (roughly 1,500 notification events/second) without re-architecting.

The team of six engineers (three senior, three mid-level) has no dedicated infrastructure engineer and no existing Kafka expertise. Redis is already running in production for session storage and rate limiting. Budget is modest — managed Kafka (Confluent Cloud) is not affordable at full scale.

## Decision

> We will use **Redis Streams** on the existing Redis infrastructure for the notification message broker.

Producers will `XADD` notification events to typed streams (`notifications:email`, `notifications:webhook`, `notifications:billing`). Consumer groups will process each stream independently, using `XREADGROUP` for consumption, `XACK` for acknowledgment, and `XCLAIM` for pending-message recovery. Failed messages exceeding the retry budget will be written to a dead-letter stream for manual inspection.

The existing Redis cluster will host streams alongside the current session storage and rate-limiting workloads. A separate Redis instance or dedicated logical database should be provisioned if contention becomes measurable — but this is an operational adjustment, not an architectural change.

Billing notifications will achieve exactly-once delivery via an application-layer idempotency key pattern: the producer attaches a unique idempotency key (derived from the triggering event's identity), and the consumer records processed keys in a durable deduplication set (backed by PostgreSQL or Redis with RDB/AOF persistence) before acting.

## Rationale

**Existing infrastructure, zero operational tax.** Redis is already deployed, monitored, and understood by the team. Adding streams introduces no new binaries, no new deployment pipelines, no new security-group rules, and no new on-call runbooks. Every minute spent learning Kafka's consumer-group rebalancing protocol, partition assignment strategy, ZooKeeper/KRaft health, and log compaction is a minute not spent delivering the feature that the business needs in two weeks.

**Delivery timeline fits the constraint.** A minimal Redis Streams pipeline (producer `XADD` → consumer `XREADGROUP` → `XACK` → DLQ) can be prototyped in an afternoon and shipping to production within the first week. Kafka, by contrast, requires provisioning brokers, configuring topic replication, tuning producer/consumer client settings, and setting up monitoring for consumer lag, disk throughput, and partition health — none of which the team has done before. The two-week setup constraint rules out Kafka.

**Throughput is not the bottleneck.** At 10x growth, the system will produce ~15,000 notification events per second across three streams. A single Redis node handles 100,000+ ops/second on modest EC2 instances. Kafka's 100k+ messages/second per partition advantage is irrelevant at this scale — it buys headroom the system does not need, at a complexity cost the team cannot absorb.

**Exactly-once at the application layer is more auditable than Kafka's protocol-level EOS.** Kafka's exactly-once semantics require idempotent producers, transactional coordinators, and read-committed isolation — a constellation of configuration flags that is easy to misconfigure and hard to debug when it fails silently. The idempotency-key approach (producer generates a deterministic key → consumer checks a dedup set before processing) is trivial to reason about, log, and test. The dedup set doubles as an audit trail for billing events.

**Future WebSocket push simplifies on the same infrastructure.** Real-time push requires a pub/sub channel fanning out to connected WebSocket clients. Redis Pub/Sub is a proven pattern for this and operates on the same Redis connection pool the streams already use. Kafka would require a separate WebSocket bridge service with its own consumer group management and connection-state tracking.

## Consequences

### Positive

- **No provisioning delay.** The broker already exists in production. Implementation starts on day one.
- **Minimal cognitive load for a 6-person team.** Every engineer can reason about `XADD`/`XREADGROUP`/`XACK` by reading the Redis docs for an afternoon. No one needs to understand partition leaders, ISR replication, or consumer rebalance protocols.
- **Retry and DLQ are built on primitives the team already monitors.** Pending entries in consumer groups (`XPENDING`) naturally track in-flight messages. A dead-letter stream is just another stream key — no special infrastructure.
- **WebSocket push shares the Redis connection pool.** Adding real-time push does not introduce a new message broker or a new stateful service.
- **Operational cost is near zero.** Redis streams consume negligible additional memory at this scale. No new EC2 instances, no managed-service bill.

### Negative

- **No long-term message retention.** Redis streams evict messages by `MAXLEN` or when memory is full. There is no time-based retention policy. Messages consumed and acknowledged are gone. Event replay for debugging requires application-level logging or a separate archival pipeline.
- **Consumer group rebalancing is manual.** When a consumer joins or leaves a group, partition assignment does not rebalance automatically as it does in Kafka. The team must either pin consumers to streams by convention or implement a simple coordination layer. At the current and near-term scale (three streams, two to five consumers each), this is a naming convention, not a distributed-systems problem.
- **No native exactly-once semantics.** Exactly-once must be implemented at the application layer via idempotency keys. This is straightforward but requires discipline — every consumer must check the dedup set before processing, and the dedup set must be backed by durable storage.
- **Scale ceiling below Kafka.** Beyond ~50,000 events/second per Redis node or when stream memory exceeds available RAM, the system will need Redis Cluster or a migration. This ceiling is 3x above the 10x growth target. If the business scales beyond that, a migration to Kafka (or a sharded Redis Cluster) is a known future work item, not an emergency.

### Follow-ups

1. **Provision a separate logical database (Redis db 1)** for streams to avoid eviction pressure from the session cache.
2. **Define the idempotency key schema** for billing events: `billing:<event_type>:<task_id>:<timestamp_slot>` so retries produce the same key.
3. **Implement the deduplication table** in PostgreSQL (a `processed_events` table with a unique constraint on the idempotency key) as the source of truth for exactly-once checks.
4. **Ship a single-stream prototype** (email notifications) and validate latency reduction before expanding to webhook and billing streams.
5. **Monitor stream length and pending-entry count** via existing Redis metrics collection; alert when any stream exceeds 10,000 pending entries.

## Alternatives Considered

- **Apache Kafka** — Rejected because the operational cost exceeds the problem's needs. Kafka provides superior ordering guarantees within partitions, configurable time-based retention, automatic consumer rebalancing, and protocol-level exactly-once semantics. However, it requires dedicated brokers (minimum three for production), ZooKeeper or KRaft, daily monitoring of disk throughput and consumer lag, and a team that understands partition leadership and ISR replication. The team of six has no existing Kafka expertise, zero Kafka infrastructure in production, and a two-week delivery constraint. Kafka's strengths (multi-hundred-thousand-messages-per-second throughput, multi-year retention, multi-subscriber replay) are not required at the target scale of ~15,000 events/second and a notification system where messages are processed and discarded. Self-hosting Kafka would consume 2–3 weeks of setup before any application code ships; managed Confluent Cloud exceeds the budget. This is the right choice for a system that needs event sourcing, long-term audit streams, or 100k+ events/sec — our notification subsystem does not.
- **Amazon SQS + SNS** — Rejected because it introduces AWS vendor lock-in and complicates the exactly-once requirement. SQS provides at-least-once delivery with a 14-day retention window and is trivially scalable. Combined with SNS for fan-out, it covers the use case. However, SQS's at-least-once delivery (with occasional duplicates, well-documented) would require the same idempotency-key pattern as Redis Streams, without offering the low-latency Pub/Sub path that Redis provides for the upcoming WebSocket feature. SNS+SQS also add per-request costs that exceed Redis's flat infrastructure cost at 15,000 events/second. Most importantly, the team already operates Redis; adding SQS/SNS means another AWS service to learn, permission, and monitor — no operational win over streams.
- **Background workers on PostgreSQL (SKIP LOCKED + job table)** — Rejected because it couples notification throughput to the primary database's connection pool, recreating the original cascading-failure problem in a different form. A `SELECT ... FOR UPDATE SKIP LOCKED` polling loop on a notification_jobs table works at small scale but adds connection pressure, row-lock contention, and vacuum overhead to the same database whose pool exhaustion caused two incidents this year. PostgreSQL-based queues are a reasonable choice for sub-100 events/second workloads with a single consumer; our target is two orders of magnitude above that, with multiple consumer groups and retry semantics that would require an application-level retry scheduler anyway.
