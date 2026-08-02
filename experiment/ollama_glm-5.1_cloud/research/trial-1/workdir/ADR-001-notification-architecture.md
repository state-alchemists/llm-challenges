# ADR-001: Notification Subsystem Message Broker

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 MAUs and processes ~2M tasks/month, with peak traffic of ~500 req/s. Notifications (emails, webhooks) are currently handled synchronously in the HTTP request cycle, causing:

- **Request timeouts**: Average latency 800ms, spiking to 8s at peak.
- **Silent failures**: No retry or dead-letter queue when downstream providers fail.
- **Cascading failures**: Two incidents this year from slow webhooks exhausting the connection pool.
- **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") require exactly-once delivery, which we cannot provide today.

We need to decouple notification production from delivery, add retry with exponential backoff, support at-least-once delivery (exactly-once for billing), and prepare for real-time WebSocket push within two quarters. The system must handle 10x traffic growth without re-architecting.

**Constraints**:

- 6-person team (3 senior, 3 mid-level), no dedicated infra engineer.
- Redis is already in production for sessions and rate limiting.
- No team experience with Kafka.
- Setup/migration must deliver value within 2 weeks.
- Modest budget — managed Confluent Cloud at full scale is not affordable.
- Exactly-once semantics required for billing notifications.

## Decision

**We choose Redis Streams** as the message broker for the notification subsystem.

### Justification

Redis Streams satisfies every hard requirement while staying within the team's operational and budgetary constraints:

1. **Minimal setup, fast time-to-value**. Redis is already deployed and the team has operational experience with it. Adding Streams requires a Redis module upgrade (if not already on Redis ≥5.0) and library integration — achievable well within the 2-week window. Kafka would require provisioning a new cluster (self-managed: weeks of operational learning; managed: significant monthly cost).

2. **Throughput is sufficient**. At 500 req/s peak with a 10x growth target (5,000 req/s), Redis Streams comfortably handle tens of thousands of messages/second on a single instance. Kafka's superior throughput (100k+/s) is an order of magnitude beyond what we need and does not justify the operational cost.

3. **Consumer groups and ordering**. Redis Streams provide consumer groups (`XGROUP`, `XREADGROUP`) with per-consumer delivery tracking, exactly what we need for parallel notification processing. Ordering is guaranteed per-stream (per notification type), which meets our requirements. Kafka offers partition-level ordering; we do not need cross-topic ordering, so Redis's guarantee is equivalent in practice.

4. **Message retention**. Redis Streams support configurable `MAXLEN` or time-based trimming. For our use case, notifications are consumed within seconds; a 24-hour retention window with a 100K-message cap is more than sufficient. Kafka's durable log with multi-day/week retention is a capability we do not need.

5. **Exactly-once for billing**. We implement exactly-once delivery for billing notifications via:
   - **Idempotent producers**: Each billing event carries a deterministic ID (e.g., `billing:{org_id}:{event_type}:{timestamp_bucket}`). Producers check Redis for the ID before publishing via `XADD` with `NOMKSTREAM` and a dedicated dedup set (`SET NX`).
   - **Idempotent consumers**: Consumers process each message idempotently using the message ID and a deduplication table in PostgreSQL (`INSERT ... ON CONFLICT DO NOTHING`). Combined with at-least-once delivery from Redis Streams (messages remain in the stream until explicitly acknowledged via `XACK`), this achieves effectively-once processing.

   Kafka's transactional exactly-once semantics (idempotent producer + transactional consumer) are more comprehensive out of the box, but they require the Kafka transaction coordinator and careful consumer configuration. Given our scope, the application-level dedup approach is simpler to implement, verify, and debug with a 6-person team.

6. **Operational fit**. A 6-person team with no Kafka experience and no dedicated infra engineer cannot responsibly operate a Kafka cluster. Self-managed Kafka requires tuning broker configs, managing ZooKeeper/KRaft, monitoring partition rebalancing, and handling rack awareness. Redis, by contrast, is already in our runbooks and monitoring dashboards.

## Consequences

### Pros

- **Fast delivery**: Can be in production within 2 weeks with familiar tooling.
- **Low operational overhead**: No new infrastructure to provision, monitor, or staff for.
- **Cost-effective**: Redis is already paid for; no additional managed-service fees.
- **Consumer groups**: Built-in support for fan-out and parallel consumption — covers current needs and the planned WebSocket push layer.
- **At-least-once with practical exactly-once**: `XACK`-based acknowledgment plus application-level dedup delivers the billing guarantee we need.
- **Simpler failure domain**: One fewer distributed system to operate and debug.

### Cons

- **Lower message retention ceiling**: Redis Streams are memory-resident. With `MAXLEN` trimming, retention is bounded. If we later need multi-day replay or event sourcing, we would need to re-evaluate. Mitigation: archive consumed events to PostgreSQL for long-term audit.
- **No native exactly-once semantics**: We achieve it at the application layer (idempotent producers + idempotent consumers). This is correct but requires discipline — every new producer/consumer must follow the dedup pattern. Mitigation: provide a shared library that encapsulates the pattern.
- **Scaling ceiling**: A single Redis node handles tens of thousands of messages/second. At true massive scale (100k+ req/s sustained), Redis Streams would become a bottleneck and Kafka would be the right choice. That ceiling is well above our 10x growth target.
- **No partition-level parallelism**: A Redis Stream is a single logical partition. Consumer groups distribute across consumers, but there is no Kafka-style multi-partition parallelism within one stream. Mitigation: use multiple streams (one per notification priority tier) if parallelism becomes a concern.
- **Persistence model**: Redis persistence (RDB snapshots + AOF) offers durability, but it is not equivalent to Kafka's commit log. Under extreme failure scenarios (simultaneous primary and replica loss with AOF corruption), recent messages could be lost. Mitigation: enable AOF with `appendfsync everysec`, use a replica, and rely on the at-least-once retry pattern to recover.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for event streaming and would meet our throughput and growth requirements handily. Its strengths for our use case:

- **Exactly-once semantics**: Native transactional producers and consumers, eliminating the need for application-level dedup.
- **Superior retention**: Durable, disk-based commit log with configurable retention (days/weeks). Enables full event replay without database archiving.
- **Proven at scale**: 10x, 100x growth would not require re-architecting.
- **Rich ecosystem**: Kafka Connect, schema registry, mature client libraries.

**Why we rejected it**:

- **Operational complexity**: Self-managed Kafka requires provisioning brokers, tuning partitions, managing KRaft/ZooKeeper, and monitoring consumer lag — a non-trivial operational burden for a 6-person team with no Kafka experience and no dedicated infra engineer. This risk alone is disqualifying.
- **Cost**: Managed Kafka (Confluent Cloud, AWS MSK) at our throughput tier would cost $500–$1,500/month minimum, well beyond our modest budget. Self-hosted requires EC2 instances, EBS volumes, and operational insurance that also costs more than Redis.
- **Time-to-value**: Setting up Kafka (cluster provisioning, security, client library learning, consumer group tuning) would exceed our 2-week window before delivering any user-facing value.
- **Over-engineering for current scale**: Kafka's capabilities exceed our needs by an order of magnitude. The throughput, retention, and partitioning guarantees it provides are solutions to problems we do not yet have and are unlikely to hit within the 10x growth window.

Kafka becomes the right choice if/when we exceed Redis Streams' practical limits or acquire dedicated infrastructure expertise. That decision can be revisited as a future ADR — Redis Streams' consumer group model maps cleanly to Kafka consumer groups, making migration straightforward.