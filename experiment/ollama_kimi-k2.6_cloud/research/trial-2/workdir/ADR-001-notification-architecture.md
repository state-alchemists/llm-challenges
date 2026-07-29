# ADR-001: Notification Architecture — Async Message Broker Selection

**Status:** Proposed

**Context:**

The Notifier subsystem currently sends emails and webhooks synchronously within the Flask HTTP request cycle. At 85,000 MAU and peak loads of ~500 req/s, this has produced:

- Average notification latency of 800ms, spiking to 8s during peaks.
- Silent failures with no retry or dead-letter queue.
- Two production incidents where slow webhook endpoints caused connection pool exhaustion and cascading failures.
- No delivery guarantees for billing-critical events (e.g., "payment failed"), which must be delivered exactly once.

We must decouple notification dispatch from HTTP requests, introduce retry with exponential backoff, and prepare for real-time WebSocket pushes within two quarters. The system must also support 10× traffic growth without re-architecting.

**Constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already runs in production for sessions and rate limiting.
- No Kafka experience on the team.
- Migration must deliver value within 2 weeks.
- Modest budget; managed Confluent Cloud is unaffordable at scale.
- Exactly-once semantics are mandatory for billing notifications.

**Decision:**

Adopt **Redis Streams** as the async message broker for the notification subsystem.

**Justification:**

1. **Operational complexity and team constraints.** Kafka is operationally demanding: a production HA deployment requires at least three brokers, ZooKeeper or KRaft quorum management, JVM tuning, ISR monitoring, and careful partition rebalancing. Our team has no Kafka experience and no dedicated infrastructure engineer. Redis is already production-hardened for sessions and rate limiting; the team has existing runbooks, monitoring, and backup procedures. This satisfies the 2-week delivery constraint with minimal risk.

2. **Throughput suitability.** Current peak load is ~500 req/s; the 10× target is ~5,000 req/s. A single Redis instance routinely handles >100,000 operations per second. Notification payloads are small JSON documents; even with 10× growth, Redis Streams will not be the throughput bottleneck.

3. **Ordering guarantees.** Redis Streams provides strict, per-stream ordering (messages are append-only and monotonically ID'd). For our use case—task assignment emails, webhook dispatches, and billing alerts—per-notification-type streams give sufficient ordering without the complexity of topic partitioning.

4. **Message retention.** Redis retention is memory-bound (configurable via `MAXLEN` or `MAXLEN ~` trimming). This is acceptable because notifications are ephemeral: they are processed by workers and acked within seconds or minutes. We do not need multi-day disk-based replay for this workload. Aggressive trimming keeps memory predictable.

5. **Consumer groups and retry.** Redis Streams natively supports consumer groups (`XREADGROUP`), automatic message claiming for failed consumers (`XPENDING`, `XCLAIM`), and individual message acknowledgement. This gives us the building blocks for at-least-once delivery with exponential-backoff retry and dead-letter behavior for repeatedly failed messages.

6. **Exactly-once semantics for billing.** True exactly-once requires idempotency at the consumer, because external systems (SMTP, webhook endpoints) do not participate in broker transactions. We will implement application-level deduplication: before processing a billing notification, the worker attempts an atomic insert into a PostgreSQL idempotency table keyed by event ID. If the insert succeeds, the notification is sent and the Redis message is acked. This pattern works with either broker, but Redis Streams' simple at-least-once semantics make the boundary explicit and easy to reason about, whereas Kafka's transactional exactly-once adds client-side complexity (transactions API, `isolation.level`) that our team lacks experience to operate safely.

7. **Future WebSocket push.** Redis already supports Pub/Sub. Adding WebSocket fan-out in the next two quarters requires no new infrastructure if we stay in the Redis ecosystem.

8. **Cost.** Redis Streams can run on our existing Redis instance or a small, dedicated ElastiCache node. Kafka would require a minimum of three EC2 instances (or paid managed service), violating our modest budget.

**Consequences:**

*Pros:*
- **Rapid time to value:** Existing Redis expertise and infrastructure allow a 2-week migration.
- **Low operational overhead:** Reuses current monitoring, alerting, and backup procedures.
- **Sufficient scale:** 10× growth (5,000 msg/s) is well within single-node Redis capacity for this payload size.
- **Unified stack:** Sessions, rate limiting, async notifications, and future WebSockets all live in one operational surface.
- **Consumer group scaling:** We can horizontally scale Flask worker processes by adding more consumers to the same Redis consumer group.

*Cons:*
- **Memory-bound retention:** If business requirements change to require multi-day message replay, we will need an external archival solution or migrate to a disk-backed broker.
- **No native stream partitioning:** Vertical scaling of a single Redis instance (or migration to Redis Cluster) is the path for growth beyond ~10,000–50,000 msg/s, whereas Kafka scales horizontally via partitions. Given our 5,000 msg/s target, this is acceptable today.
- **Application-level exactly-once:** We must build and maintain the PostgreSQL idempotency table and deduplication logic; the broker does not provide transactional exactly-once abstractions.
- **Blast radius:** Running notifications on the same Redis used for sessions increases load. We should deploy a dedicated Redis/Stream node if memory or CPU pressure arises.
- **Ecosystem gaps:** No equivalent to Kafka Connect for third-party integrations; we will write small Python workers instead.

**Alternatives Considered:**

**Apache Kafka**
- Kafka offers superior disk-based retention, mature consumer rebalancing, and formal exactly-once primitives (idempotent producers, transactions, `read_committed` isolation).
- **Rejected:** The team has zero production Kafka experience, and self-hosting an HA Kafka cluster is operationally incompatible with a 6-person team that has no infrastructure engineer. It would exceed the 2-week value-delivery deadline and require ongoing tuning and partition management. Furthermore, our 10× throughput target (~5,000 msg/s) does not approach the scale where Kafka's horizontal partitioning advantage becomes necessary. The operational cost and risk outweigh the technical benefits for our current constraints.
