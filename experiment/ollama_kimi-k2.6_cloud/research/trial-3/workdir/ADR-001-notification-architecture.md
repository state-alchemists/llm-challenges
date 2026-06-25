# ADR-001: Notification Architecture — Redis Streams

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users and creates ~2M tasks per month, with peak HTTP traffic of ~500 req/s. Notifications (emails, webhooks) are currently processed synchronously inside the Flask HTTP request cycle. This has produced four critical failure modes:

1. **Request timeouts**: Blocking I/O pushes average latency to 800ms and spikes to 8s during business hours.
2. **Silent failures**: Downstream email providers or webhook endpoints drop messages with no retry or dead-letter queue.
3. **Cascading failures**: Slow webhook endpoints have twice caused connection pool exhaustion, degrading unrelated features.
4. **No delivery guarantees**: Billing-critical events (trial expiry, payment failure) risk duplicate or dropped delivery.

We must decouple notification work from the request cycle, add exponential-backoff retry, guarantee at-least-once delivery for all events, and preserve exactly-once semantics for billing events. Within two quarters we also intend to add real-time WebSocket push. Our scaling target is 10× traffic growth (~5,000 req/s peak) without re-architecting the messaging layer.

**Team constraints** shape this decision:

- Six engineers (three senior, three mid-level), no dedicated infrastructure engineer.
- Redis is already in production for session storage and rate limiting.
- No prior operational experience with Kafka.
- Budget is modest; managed Kafka (Confluent Cloud) is not viable at target scale.
- The solution must ship within two weeks.

## Decision

**We will use Redis Streams as the notification message bus.**

The existing Redis instance will be promoted to a dual-purpose store: it will continue to serve sessions and rate limiting, and it will gain a new responsibility as the notification stream backend. Producers will use `XADD` to enqueue events. Consumers will run as background worker processes (e.g., Celery or a lightweight Python daemon) using `XREADGROUP`, `XACK`, `XPENDING`, and `XCLAIM` to implement at-least-once delivery with automatic retry and dead-letter semantics.

**Exactly-once for billing notifications will be enforced at the application layer**, not the broker layer. Every billing event will carry a deterministic idempotency key (a UUIDv5 derived from the event type, entity ID, and timestamp bucket). The consumer will attempt to insert the processed event into a PostgreSQL table guarded by a `UNIQUE` constraint on that key. A duplicate message will trigger a uniqueness violation and be acknowledged without side effects. This pattern is simpler for our stack than broker-level transactions and is sufficient for our volume.

Redis Streams supports consumer groups, stream-level FIFO ordering, and message claiming for failed consumers, all of which satisfy our retry and ordering requirements. Because Redis is already operated in production (AOF persistence, RDB snapshots, monitoring, failover runbooks), adding Streams requires no new infrastructure software, no new operational expertise, and minimal provisioning time.

## Consequences

### Pros

- **Operational continuity**: We reuse existing Redis infrastructure, monitoring, backups, and team expertise. No new service to deploy, tune, or page someone for at 3 a.m.
- **Speed to value**: Streams can be enabled on the current Redis instance in hours. A two-week migration window is realistic.
- **Throughput headroom**: Redis Streams handles ~50,000 messages/sec per node. Our 10× target of ~5,000 req/s peak leaves an order-of-magnitude margin.
- **Ordering guarantees**: Stream-level FIFO ordering ensures that, for a given stream, consumers process messages in the order they were produced.
- **Consumer-group semantics**: `XREADGROUP`, `XACK`, and `XCLAIM` provide the primitives needed for competing consumers, automatic re-delivery of unacknowledged messages, and dead-letter extraction.
- **WebSocket synergy**: Redis Pub/Sub (already available on the same instance) gives us a low-latency path to real-time WebSocket push within the same operational footprint.
- **Cost**: Zero additional infrastructure licensing or managed-service fees.

### Cons

- **Memory-bound retention**: Redis Streams is primarily memory-resident. Long backlogs or large dead-letter queues can pressure RAM. We will mitigate this with explicit stream trimming (`MAXLEN` or `MINID`) and by moving dead-lettered events to PostgreSQL after a bounded number of retry attempts.
- **Weaker exactly-once primitives**: Unlike Kafka, Redis Streams does not offer idempotent producers or transactional exactly-once semantics. Application-level deduplication is mandatory and must be maintained correctly.
- **Less mature ecosystem**: There is no Kafka Connect, Schema Registry, or ksqlDB equivalent. We will build lightweight Python consumers rather than leveraging a mature connector ecosystem.
- **Single-node risk**: Our current Redis deployment is a single primary. If it becomes a bottleneck under 10× load, we may need to shard or migrate to Redis Cluster. This is a known, bounded risk.
- **Consumer rebalancing**: Redis Streams consumer-group rebalancing is less sophisticated than Kafka’s. We must ensure worker processes handle `XREADGROUP` blocking semantics carefully to avoid duplicate deliveries during scaling events.

## Alternatives Considered

### Apache Kafka

We evaluated Kafka because of its industry reputation for high-throughput streaming, durable disk-based retention, and native exactly-once semantics (idempotent producers + transactions).

**Why we rejected it:**

- **Operational complexity**: Kafka (or KRaft) requires broker provisioning, replication-factor tuning, partition balancing, and JVM operational expertise. Our six-person team has no prior Kafka experience and no dedicated infrastructure engineer to own on-call.
- **Setup timeline**: A production-ready, safely configured Kafka cluster—including monitoring, alerting, and consumer-group validation—cannot be built, tested, and deployed by a part-time effort inside two weeks.
- **Cost**: Self-hosted Kafka is free, but the engineering time cost is high. Managed Kafka (MSK, Confluent Cloud) exceeds our modest budget at 10× scale.
- **Overkill for current scale**: Our peak is 500 req/s; 10× is 5,000 req/s. Kafka shines at 50,000–500,000+ req/s. The operational tax is not justified by the throughput requirement.
- **Exactly-once is still end-to-end**: Kafka’s exactly-once semantics apply to the broker-to-consumer handoff. If the consumer writes to PostgreSQL, idempotency is still required at the application layer to guard against consumer-restart duplicates. Since we would still need application-level deduplication, Kafka’s broker-level advantage is marginal for our use case.

**Verdict**: Kafka is the superior technology at hyperscale, but for our team size, budget, timeline, and throughput envelope, it introduces more operational risk than it mitigates. Redis Streams provides the necessary messaging primitives within our existing operational boundary, and we can migrate to Kafka later if we outgrow it.
