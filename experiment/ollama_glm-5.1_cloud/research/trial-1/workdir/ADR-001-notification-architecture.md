# ADR-001: Notification Subsystem Message Broker

## Status

Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, peak 500 req/s) handles notifications — emails and webhooks on task updates, assignments, and completions — synchronously inside the HTTP request cycle. This has led to request timeouts (average 800 ms, spiking to 8 s), silent failures with no retry or dead-letter queue, two cascading outages from slow webhook endpoints exhausting the DB connection pool, and no delivery guarantees for billing-critical notifications.

We need to decouple notification production from the request cycle into an asynchronous message broker that supports:

- **Retry with exponential backoff** and a dead-letter queue for failed deliveries.
- **At-least-once delivery** for all notifications; **exactly-once semantics** for billing events (trial expired, payment failed).
- **Real-time WebSocket push** within 2 quarters.
- **10x traffic growth** (~5,000 req/s peak, proportionally more notification events) without re-architecting the broker layer.

Hard constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Experience**: Redis is already in production for sessions and rate limiting. No one has Kafka operational experience.
- **Time to value**: Must deliver measurable improvement within 2 weeks of starting migration.
- **Budget**: Modest — managed Confluent Cloud at full scale is not affordable today.

Two candidates are on the table: **Apache Kafka** and **Redis Streams**.

## Decision

We choose **Redis Streams** as the message broker for the notification subsystem.

### Justification

| Criterion | Redis Streams | Apache Kafka |
|---|---|---|
| **Operational footprint** | Zero incremental infra — Redis is already running. Add a second instance for persistence isolation if desired. | New cluster: 3+ brokers minimum, ZooKeeper or KRaft, monitoring, tuning. |
| **Team experience** | Redis is already in use (sessions, rate limiting). Streams API is straightforward. | No operational Kafka experience on the team. |
| **Time to value** | Days: consumer group creation is one `XGROUP` call; the Flask app produces with `XADD` and consumes with `XREADGROUP`. | Weeks to months: cluster provisioning, topic design, partition strategy, producer/consumer config tuning, monitoring setup. |
| **Throughput** | Single-node Redis handles 500K–1M+ commands/s on modern hardware. Projected 10x peak (~5,000 req/s, yielding perhaps 2,000–3,000 notification events/s) is well within headroom. | Higher ceiling (millions of messages/s), but we will not approach it for years. |
| **Ordering guarantees** | Strict per-stream ordering (all consumers see the same sequence). Sufficient — we partition by channel (e.g., `notifications:billing`, `notifications:webhooks`) and ordering within a channel is what matters. | Per-partition ordering; requires careful partition-key design to avoid cross-partition ordering issues. |
| **Message retention** | `MAXLEN` trims the stream; typical retention of hours to a few days is trivial. Notifications are processed within seconds; long retention is not required. | Configurable time-based retention (days to weeks). More than we need for this use case. |
| **Consumer groups** | First-class since Redis 5.0 (`XGROUP`, `XREADGROUP`, `XPENDING`, `XCLAIM`). Supports group-level balancing, pending-entry recovery, and dead-letter redirection. | Industry-standard consumer groups with partition assignment, rebalancing, and offset management. |
| **Exactly-once semantics** | At-least-once delivery. Effective exactly-once is achieved by **application-level idempotency**: each billing notification carries a unique `notification_id`, and the consumer deduplicates against a PostgreSQL table before acting. This is required regardless of broker — true exactly-once across an external system boundary (email provider, webhook endpoint) is impossible; only the application can enforce it. | Kafka Transactions provide exactly-once *within Kafka itself* (producer → broker → consumer). At the system boundary (SMTP, HTTP webhook), you still need application-level idempotency. The broker-level EOS does not eliminate the deduplication requirement for our use case. |
| **Operational complexity** | Low. One process to monitor, one config to tune. Failover via Redis Sentinel or cluster mode — same operational pattern the team already manages. | High. Broker lifecycle, partition rebalancing, under-replicated partitions, ISR management, GC tuning (JVM), security (SASL/TLS). Without a dedicated infra engineer, this is a significant risk. |
| **Cost** | Marginal — we already pay for Redis. A second dedicated instance for streams isolation is ~$50–100/month on AWS ElastiCache. | Self-managed: 3+ EC2 instances, EBS, operational toil. Managed (MSK/Confluent): $500+/month at modest throughput, scaling higher — explicitly out of budget. |

The decisive factors are **time to value**, **operational risk**, and **cost**. Kafka's superior throughput ceiling and broker-level transactions are advantages we cannot exploit under our constraints: our projected load is two orders of magnitude below Redis Streams' capacity, and broker-level exactly-once does not solve the boundary problem that actually matters (idempotent delivery to email/webhook providers). What Kafka does add — operational complexity, JVM tuning, partition management, weeks of setup — directly violates our 2-week delivery window and 6-person team capacity.

Redis Streams gives us a working consumer-group system in days, with an operational model the team already knows, at marginal cost, and with ample headroom for 10x growth.

## Consequences

### Pros

- **Immediate decoupling**: Notification production moves out of the HTTP request cycle within days, directly addressing the timeout and cascading-failure problems.
- **Low operational risk**: No new infrastructure to learn, provision, or operate. The team already manages Redis.
- **Cost-effective**: Near-zero incremental spend. A dedicated Redis instance for streams isolation is optional and cheap.
- **Sufficient performance**: Redis Streams handles orders of magnitude more than our 10x growth target. No re-architect needed.
- **Consumer groups built in**: `XREADGROUP` with `XPENDING`/`XCLAIM` provides retry semantics, dead-letter handling, and consumer failover out of the box.
- **WebSocket path**: Redis Pub/Sub or Streams are the standard fan-out mechanism for WebSocket servers (e.g., `socket.io` Redis adapter). The same Redis instance serves both async notification processing and real-time push.

### Cons

- **Persistence trade-off**: Redis is primarily in-memory. With AOF persistence enabled (which we will configure), data survives restarts, but the retention window is shorter than Kafka's disk-based log. This is acceptable — notifications are processed within seconds and we persist the canonical state in PostgreSQL — but it means Redis Streams are not suitable as a long-term event-sourcing store.
- **At-most-1,000 consumer groups per stream**: A Redis implementation detail. We will use a small number of channels (billing, email, webhook, push) each with one consumer group, so this is not a constraint in practice.
- **No native schema registry**: Message formats are application-contract. We will enforce schema stability via versioned payload structures in the Flask codebase and document them in the project README. If schema evolution becomes complex later, we can migrate to Protobuf/Avro with a thin validation layer — but YAGNI for now.
- **Cluster mode limits**: Redis Cluster does not support multi-key operations across slots. Our design uses separate stream keys per channel, so this is not an issue. If we later need atomic multi-stream transactions, we would need to co-locate keys on the same slot via hash tags — a known pattern, not a blocker.
- **Migration ceiling**: If we ever reach a scale where a single Redis node cannot handle notification throughput (unlikely at even 100x current load), we would need to migrate to Kafka. This is a theoretical concern — Redis Streams on appropriate hardware handles millions of messages per second — but it should be acknowledged. The consumer-group and channel design we adopt now maps cleanly to Kafka topics and consumer groups, making a future migration straightforward.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for event streaming at scale. We evaluated it seriously because of its maturity, ecosystem, and broker-level exactly-once semantics.

**Reasons for rejection given our constraints:**

1. **Operational overhead exceeds team capacity.** A production Kafka deployment requires 3+ brokers, ZooKeeper or KRaft controllers, monitoring (under-replicated partitions, ISR lag, consumer lag), JVM tuning, and security configuration. With no dedicated infrastructure engineer and no prior Kafka experience, the team would spend weeks achieving a production-ready setup — violating the 2-week delivery window.

2. **Broker-level exactly-once does not solve our boundary problem.** Kafka Transactions guarantee exactly-once delivery from producer to consumer *within Kafka*. Our delivery boundary is external (SMTP servers, third-party webhook endpoints). At that boundary, only application-level idempotency (deduplication via `notification_id` against PostgreSQL) can guarantee exactly-once processing. Since we must implement that deduplication layer regardless, Kafka's intra-broker EOS provides no marginal benefit for this use case.

3. **Cost.** Managed Kafka (Confluent Cloud, AWS MSK) starts at ~$500/month for minimal throughput and scales upward — explicitly excluded by our budget. Self-managed Kafka shifts cost into engineering time (provisioning, tuning, incident response) that our 6-person team cannot afford.

4. **Over-engineered for current and projected scale.** Kafka's design targets millions of events per second with multi-terabyte retention. Our projected 10x peak is ~2,000–3,000 notification events per second with seconds-to-minutes processing latency. Redis Streams handles this with room to spare; Kafka's capacity advantage is unused.

5. **Migration friction.** Should we ever need Kafka (e.g., for a broader event-sourcing platform beyond notifications), our Redis Streams design — discrete channels, consumer groups, idempotent consumers — maps one-to-one to Kafka topics and consumer groups. The migration path is well-understood and can be undertaken when the team has the capacity, not under time pressure.

### Other alternatives briefly considered

- **RabbitMQ**: Strong routing and dead-letter support, but introduces a new operational component the team has no experience with. Redis Streams provides equivalent consumer-group semantics without adding infrastructure.
- **SQS + SNS**: Fully managed, zero ops, but lacks consumer groups (SQS) and ordering guarantees (SNS FIFO has 300 msg/s limits). Would require per-consumer queue plumbing. Redis Streams is simpler and faster for our use case.
- **Celery (with Redis broker)**: Adds a heavy dependency and opinionated task model. We need a stream abstraction for future WebSocket fan-out, not just a task queue. Redis Streams is a more general foundation.