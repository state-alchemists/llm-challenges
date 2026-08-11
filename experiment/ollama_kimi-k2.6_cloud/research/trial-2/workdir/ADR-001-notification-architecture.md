# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context

The notifications module in our SaaS project management platform currently sends emails and webhooks synchronously inside the HTTP request cycle. At 85,000 monthly active users, ~2M tasks created per month, and peaks of ~500 req/s, this has caused:

1. **Request timeouts**: Average notification latency of 800ms, spiking to 8s during peak hours.
2. **Silent failures**: Dropped notifications when email providers or webhook endpoints fail, with no retry mechanism or dead-letter queue.
3. **Cascading failures**: Two incidents this year where slow webhook endpoints exhausted connection pools, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") must be delivered exactly once, but the current system offers no such guarantee.

We must decouple notifications from the HTTP request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), and lay groundwork for real-time WebSocket push notifications within two quarters. The solution must accommodate 10× traffic growth without re-architecting.

Constraints:
- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Infrastructure**: Python/Flask monolith on AWS, PostgreSQL primary + read replica, Redis already in production for session storage and rate limiting.
- **Experience**: No Kafka experience on the team.
- **Timeline**: Must deliver value within 2 weeks.
- **Budget**: Modest; managed Kafka (Confluent Cloud, AWS MSK) is not affordable at full scale today.

## Decision

We will adopt **Redis Streams** as the notification event backbone.

This choice prioritizes operational fit over raw feature superiority. Redis Streams meets our throughput requirements, provides the ordering and consumer-group primitives we need, and can be deployed immediately on our existing Redis infrastructure. The team’s existing Redis operational expertise eliminates the onboarding risk that a self-hosted Kafka deployment would impose on a 6-person team without dedicated infrastructure support.

For billing-critical notifications requiring exactly-once semantics, we will implement application-level idempotency: consumers persist processed event IDs in PostgreSQL with a unique constraint on `(event_type, entity_id, timestamp_bucket)`. This compensates for Redis Streams’ lack of broker-native exactly-once transactions. Billing events are low-volume compared to task notifications, so the deduplication overhead is negligible.

## Consequences

**Pros**
- **Operational simplicity**: Redis is already a production dependency operated by the team. Adding Streams is an API change, not a new infrastructure component. Monitoring, backup, and failover patterns remain unchanged.
- **Time-to-value**: Because Redis is already running, we can begin emitting and consuming events within days, fitting the 2-week delivery constraint.
- **Throughput headroom**: Redis handles 100K+ ops/sec on modest hardware. Our expected notification volume translates to roughly 50–100 events/sec at peak today; at 10× growth this remains well below Redis saturation.
- **Ordering guarantees**: Redis Streams preserves strict FIFO ordering within a single stream. We will use separate streams for billing vs. general notifications, ensuring billing events remain ordered per account.
- **Consumer groups**: Redis Streams supports consumer groups (`XGROUP`, `XREADGROUP`) with automatic acknowledgment tracking and the Pending Entries List (PEL) for replay. This gives us parallel consumers, automatic load balancing, and built-in retry mechanics.
- **Path to WebSocket**: Redis Pub/Sub runs alongside Streams on the same infrastructure, providing a unified platform for async job queues and real-time fan-out without introducing another service.
- **Cost**: No additional infrastructure or managed-service fees beyond our existing Redis footprint.

**Cons**
- **Exactly-once limitations**: Redis Streams does not provide broker-native exactly-once semantics (no idempotent producers or multi-stream transactions). We accept the burden of application-level deduplication for billing events.
- **Retention constraints**: Message retention is memory-bound (`XTRIM` / `MAXLEN`). We must actively trim streams and archive billing events to PostgreSQL for long-term audit compliance. Disk-based logs (e.g., Kafka) would offer cheaper, longer retention natively.
- **Ecosystem maturity**: Redis Streams lacks the rich stream-processing ecosystem of Kafka (no built-in stream joins, windowed aggregations, or mature connector framework). If notification logic evolves into complex event processing, we may outgrow Redis.
- **Scaling ceiling**: While 10× growth fits comfortably, sustained rates beyond ~5,000 notification events/sec would require manual stream sharding or a future migration to Kafka. We accept this as a known threshold for re-evaluation.
- **Durability model**: Redis persistence (AOF/RDB) is operationally sound but conceptually different from Kafka’s immutable append-only log. A misconfigured `appendfsync` or snapshot policy carries higher data-loss risk than Kafka’s replicated log segments.

## Alternatives Considered

**Apache Kafka**

We rejected Apache Kafka because its operational burden exceeds our team capacity and budget:

- **Operational complexity**: Self-hosted Kafka requires broker provisioning, KRaft or ZooKeeper coordination, partition rebalancing, replication-factor tuning, and dedicated monitoring. A 6-person team without an infrastructure engineer cannot safely operate this for billing-critical data.
- **Experience gap**: The team has zero Kafka experience. The risk of misconfiguration—such as enabling unclean leader elections or misunderstanding producer acknowledgments—translates directly to data-loss scenarios for billing notifications.
- **Budget constraint**: Managed Kafka (Confluent Cloud, AWS MSK) provides the operational safety we need, but our modest budget cannot afford it at target scale. Self-hosted is the only viable path, and that path is too risky given our constraints.
- **Delivery timeline**: A production-ready Kafka deployment, including client library integration, consumer group setup, operational runbooks, and team training, would exceed the 2-week value-delivery window.
- **Technical advantages acknowledged**: Kafka offers superior broker-level exactly-once semantics (idempotent producers + transactions), unbounded disk-based retention, and higher throughput ceilings. These advantages are real but not immediately required given our volumes. If we outgrow Redis Streams, we will migrate to Kafka with the operational experience and revenue to support it.
