# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project-management platform handles ~500 req/s at peak and generates ~2M task events per month. Notifications (emails, webhooks, and soon WebSocket pushes) are currently processed synchronously inside the HTTP request cycle. This has produced four acute problems:

1. **Request timeouts** — Average latency 800 ms, spiking to 8 s during peak hours because the thread blocks until the SMTP/webhook call completes.
2. **Silent failures** — No retry mechanism; downstream outages silently drop messages.
3. **Cascading failures** — Slow webhook endpoints have twice exhausted the Flask connection pool and degraded unrelated features.
4. **No delivery guarantees** — Billing-critical events (e.g., "payment failed") can be lost or duplicated, which is unacceptable.

Our scaling targets require:
- Async decoupling of notifications from HTTP requests.
- Retry with exponential backoff.
- At-least-once delivery for general events; exactly-once semantics for billing events.
- Real-time WebSocket push within two quarters.
- Headroom for 10× traffic growth (~5,000 req/s).

We operate under hard constraints:
- Engineering team of six (three senior, three mid-level), **no dedicated infrastructure engineer**.
- Redis is already in production (session storage, rate limiting).
- **Zero** team members have production Kafka experience.
- Value must be demonstrable within **two weeks**.
- Budget is modest; managed Confluent Cloud at full scale is unaffordable.

## Decision

We will implement the notification subsystem on **Redis Streams**.

Redis Streams is the pragmatic choice because our constraints — team size, existing operational expertise, budget ceiling, and the two-week delivery window — outweigh the raw technical superiority of Kafka for our current and near-term scale.

### Justification

**Throughput**  
Redis Streams can sustain tens of thousands of messages per second per node. Our peak of ~500 req/s and 10× target of ~5,000 req/s are well within the capacity of a single properly sized Redis instance on AWS ElastiCache or EC2. Kafka can scale higher, but we do not need that headroom today.

**Ordering Guarantees**  
Redis Streams preserves total ordering of messages within a single stream. We will partition traffic by event type (e.g., `billing`, `task`, `webhook`) into separate streams. Within the billing stream, strict ordering simplifies deduplication and state-machine logic. This is equivalent to a single-partition Kafka topic and satisfies our requirements.

**Message Retention**  
Redis Streams supports explicit trimming by length or age (`XTRIM`). We will configure a maximum length per stream (e.g., 1M entries) and AOF persistence, which is adequate for a notification bus where consumers are online and long-term audit logs live in PostgreSQL. Kafka's time-based retention is richer, but we do not need indefinite log storage for ephemeral notifications.

**Consumer Groups**  
Redis Streams provides consumer-group semantics (`XREADGROUP`, `XACK`, `XPENDING`) that give us:
- Automatic message assignment across worker processes.
- Explicit acknowledgment, enabling at-least-once delivery.
- Claiming of stale messages for retry.

These primitives are less battle-tested than Kafka's rebalancing protocol, but they are sufficient for our scale and far simpler to debug when they misbehave.

**Exactly-Once Semantics for Billing**  
Neither Redis Streams nor Kafka provides magical exactly-once delivery to external systems (SMTP, webhooks). True exactly-once requires an **idempotent consumer** at the application layer. Our strategy:
1. Use Redis Streams consumer groups for at-least-once ingestion.
2. Before emitting a billing notification, check a Redis `SET` (or PostgreSQL idempotency table) keyed by `event_id`.
3. Only proceed if the key is absent; write it atomically via `SET NX`.
4. Acknowledge the stream entry only after successful external delivery.

This pattern works identically on Redis Streams and Kafka. Kafka's idempotent producer + transactions are stronger primitives, but the final safety guarantee still depends on application-level deduplication, which we must build regardless.

**Operational Complexity**  
This is the decisive factor. We already run Redis in production. Our team knows its failure modes, monitoring, backup, and tuning. Adding Redis Streams is a configuration change (`XADD`, `XREADGROUP`), not a new infrastructure vertical. Self-hosted Kafka introduces ZooKeeper or KRaft, broker replication, ISR management, partition rebalancing, and a separate monitoring/alerting surface — all of which require expertise we do not have and cannot acquire safely within two weeks. Managed Kafka is ruled out by budget.

## Consequences

### Pros

- **Rapid delivery**: We can begin async processing within days by reusing the existing Redis cluster and adding Python worker processes (e.g., via `redis-py` + `XREADGROUP`).
- **Low operational overhead**: One less datastore to monitor, back up, and on-call for. The team already knows Redis memory tuning, AOF persistence, and failover behavior.
- **Cost efficiency**: No new infrastructure spend beyond Redis capacity, which is already budgeted.
- **Adequate for 10× growth**: 5,000 req/s is comfortably inside Redis Streams throughput limits for our message sizes (~1 KB JSON payloads).
- **Path to WebSocket pushes**: Redis Pub/Sub can be layered on the same cluster for real-time WebSocket delivery in a future quarter.

### Cons

- **Not purpose-built for streaming**: Redis Streams is a data structure, not a dedicated streaming platform. Complex stream processing (windowing, joins, aggregations) would require custom code or a separate system later.
- **Memory-bound retention**: Long retention periods consume RAM. We must actively trim streams and rely on PostgreSQL for long-term audit trails. Disk-full or memory pressure events are risks we must monitor.
- **Consumer-group maturity**: Rebalancing under worker churn is less robust than Kafka. We will mitigate this by over-provisioning workers and keeping group membership stable.
- **Ecosystem gap**: No equivalent to Kafka Connect for easily wiring to external sinks; all integrations (webhooks, SMTP) require custom Python workers.
- **Future migration friction**: If we outgrow Redis Streams (e.g., need multi-datacenter replication or advanced stream processing), a migration to Kafka will require a nontrivial cutover. We accept this as deferred technical debt.

## Alternatives Considered

### Apache Kafka

We rejected Kafka because the operational and human costs exceed the marginal technical benefits for our current stage.

- **Throughput**: Kafka's partitioned log architecture offers higher throughput and better horizontal scaling. We do not need this today; 5,000 req/s is not a throughput problem for Redis Streams.
- **Ordering**: Kafka provides ordering within a partition and richer partitioning strategies. Our use case maps cleanly to a few Redis streams, so the extra flexibility is unused.
- **Retention**: Kafka's segment-based log with time/byte retention is superior for long-term replay. We do not replay notification streams; we only need a short-lived buffer.
- **Consumer groups**: Kafka's rebalancing protocol is more mature and handles worker failures gracefully. However, debugging rebalancing storms without an infrastructure engineer is dangerous given our team size.
- **Exactly-once**: Kafka offers idempotent producers and transactions, which simplify the client-side deduplication logic. Yet the final guarantee still requires idempotent consumers, and the operational complexity of running transactions correctly is high for a team with no Kafka experience.
- **Operational complexity**: Self-hosted Kafka requires ZooKeeper or KRaft, broker tuning, partition monitoring, and careful rolling upgrades. Managed Confluent Cloud is unaffordable. The two-week window makes a safe Kafka deployment unrealistic.

**Verdict**: Kafka is the technically superior streaming platform, but its adoption would violate our time, budget, and operational-expertise constraints. We will reconsider Kafka if we need complex stream processing or exceed Redis Streams' throughput ceiling in the future.
