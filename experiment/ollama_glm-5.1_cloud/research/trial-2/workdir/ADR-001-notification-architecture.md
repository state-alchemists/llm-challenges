# ADR-001 — Notification Subsystem: Redis Streams over Apache Kafka

- **Status**: Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users with ~2M tasks created per month and peak traffic of ~500 req/s. Notifications (emails, webhooks) are currently processed synchronously inside the HTTP request cycle, causing:

1. **Request timeouts** — average notification latency of 800ms, spiking to 8s at peak.
2. **Silent failures** — no retry or dead-letter queue when a downstream provider is down.
3. **Cascading failures** — two incidents this year where slow webhook endpoints exhausted the connection pool, breaking unrelated features.
4. **No delivery guarantees** — billing-critical notifications (e.g., "trial expired", "payment failed") must be delivered exactly once but currently have no such guarantee.

We must decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events where feasible), add real-time WebSocket push within two quarters, and handle 10× traffic growth without re-architecting.

Key constraints:

- **Engineering team**: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Redis** is already in production for session storage and rate limiting; the team has operational familiarity.
- **No Kafka experience** on the team today.
- **Time-to-value**: must deliver working async processing within 2 weeks of starting.
- **Budget**: modest — managed Confluent Cloud at full scale is not affordable today.
- **Exactly-once semantics** required for billing notifications.

## Decision

We will use **Redis Streams** as the message broker for the notification subsystem.

Redis Streams provides sufficient throughput and ordering guarantees for our scale, consumer group support for parallel processing, and at-least-once delivery with application-level idempotency for exactly-once billing semantics — all without introducing a new infrastructure dependency. Redis is already operated by the team, and the Streams API requires no additional broker process, JVM tuning, or partition management.

## Consequences

### Positive

- **Minimal operational footprint**: No new infrastructure component to deploy, monitor, or upgrade. Redis is already in production with established runbooks, alerting, and on-call familiarity.
- **Fast time-to-value**: The team can ship a working async notification pipeline in days, not weeks. Redis Streams commands (`XADD`, `XREADGROUP`, `XACK`, `XPENDING`) are straightforward and well-documented in the Python `redis-py` library already in our dependency tree.
- **Sufficient throughput headroom**: Redis Streams handles hundreds of thousands of messages per second on a single instance. Our current peak of ~500 req/s (and the 10× growth target of ~5,000 req/s) is well within this envelope, leaving ample margin.
- **Consumer groups for parallelism**: `XREADGROUP` with consumer groups enables horizontal scaling of notification workers without external coordination. Pending-entry lists (`XPENDING`) provide visibility into in-flight and failed messages, supporting the retry and dead-letter queue semantics we need.
- **Per-stream ordering**: Within a single stream, consumers see messages in insertion order. Partitioning notifications by type (e.g., `notifications:billing`, `notifications:webhook`) preserves ordering where it matters — billing events for a given tenant are processed sequentially.
- **Exponential backoff and retry**: `XCLAIM` allows a consumer to reclaim timed-out messages. Coupled with backoff metadata in the message payload, this supports the retry strategy we need.
- **Cost efficiency**: No additional licensing, managed service fees, or hardware provisioning. The existing Redis deployment absorbs this workload.

### Negative

- **Exactly-once is application-level, not broker-level**: Redis Streams provides at-least-once delivery. Achieving exactly-once for billing notifications requires idempotency keys in the message payload and deduplication logic in the consumer. This is implementable (store processed message IDs in Redis before executing side effects) but it is application code, not a broker guarantee — it must be designed, tested, and maintained.
- **No native long-term retention**: Redis is an in-memory store. Streams are trimmed via `MAXLEN` or time-based eviction, meaning old messages are lost once trimmed. If we need to replay weeks of notification history, we must archive to PostgreSQL or object storage separately. This is acceptable for our use case (active retry window of hours, not weeks) but is a design constraint.
- **Single-node Redis is a SPOD**: Our current Redis deployment is a single instance with no automatic failover. If Redis goes down, notifications queue in the database as a fallback. We should plan for Redis Sentinel or a managed ElastiCache cluster before relying on Streams for billing-critical delivery — this is a follow-up, not a blocker.
- **Scaling ceiling**: Redis Streams cannot match Kafka's throughput at extreme scale (millions of messages/sec across many partitions). If the platform grows beyond the projected 10× target, we may need to revisit this decision. The broker interface is abstracted behind a thin producer/consumer layer, making a future migration to Kafka feasible without re-architecting the application.
- **No native schema registry**: Message formats are implicit. We must version notification payloads explicitly and handle backward compatibility in consumer code.

### Follow-ups

1. Implement a thin `NotificationBroker` abstraction over `XADD`/`XREADGROUP`/`XACK` so the application code is decoupled from the Redis Streams API. This makes a future broker swap (e.g., to Kafka) a configuration change, not a rewrite.
2. Design the idempotency layer for billing notifications: deduplication key in message payload, processed-ID set in Redis, and at-most-once execution guard.
3. Add Redis Sentinel or migrate to AWS ElastiCache with Multi-AZ before promoting billing notifications to the Streams pipeline.
4. Implement dead-letter stream (`notifications:billing:dead`, `notifications:webhook:dead`) for messages that exhaust their retry budget.
5. Add monitoring on stream length (`XLEN`), consumer lag (`XPENDING` count), and claim rate to the existing Redis dashboards.

## Alternatives Considered

- **Apache Kafka** — Kafka provides superior throughput (millions of messages/sec), durable log-based retention with configurable expiry, native consumer group rebalancing, and transactional exactly-once semantics via idempotent producers and transactional consumers. However, it demands significant operational investment: cluster deployment (ZooKeeper or KRaft mode), JVM tuning, partition planning, monitoring (under-replicated partitions, consumer lag via Burrow or similar), and on-call expertise we do not have. Self-managed Kafka on AWS would require at least 3 broker nodes plus ZooKeeper/KRaft for production redundancy, and our modest budget rules out managed Confluent Cloud at scale. The 2-week delivery constraint is incompatible with the team's Kafka learning curve — even with a managed service, schema design, partition strategy, and consumer group management would consume the available time before delivering working notification processing. We would choose Kafka if our throughput requirements were an order of magnitude higher, if we needed multi-week message retention, or if we had a dedicated infrastructure engineer. None of those conditions hold today.