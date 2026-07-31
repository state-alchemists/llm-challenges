# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform (85,000 MAU, peak ~500 req/s) currently sends email and webhook notifications synchronously inside the HTTP request cycle. This has caused:

- **Request timeouts**: Average notification latency of 800ms, spiking to 8s during peak hours, directly degrading user experience.
- **Silent failures**: No retry mechanism exists; when an email provider or webhook endpoint is down, notifications are permanently dropped.
- **Cascading failures**: Two incidents this year where slow webhook endpoints caused connection pool exhaustion, impacting unrelated features.
- **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

We must decouple notifications from the HTTP request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), and lay groundwork for real-time WebSocket push notifications within two quarters. The system must handle 10x traffic growth without re-architecting.

**Constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis is already in production for session storage and rate limiting.
- No Kafka operational experience on the team.
- Must deliver value within 2 weeks of setup/migration work.
- Modest budget; managed Confluent Cloud is not viable at full scale today.

## Decision

We will adopt **Redis Streams** as the backbone of the notification subsystem.

**Justification:**

1. **Time to Value and Operational Reality**: Our 2-week deadline and lack of a dedicated infrastructure engineer make operational complexity the primary filter. Redis Streams operates on our existing Redis deployment (or a minimal additional Redis instance), leveraging knowledge the team already possesses. Self-hosting Kafka production-grade clusters (broker tuning, partition management, replication factor configuration, ISR monitoring, and KRaft/ZooKeeper maintenance) realistically requires weeks of setup and ongoing operational attention we do not have.

2. **Throughput Sufficiency**: Redis easily sustains 100,000+ operations per second per node. Our peak of ~500 req/s (notification events, not total traffic) and 10x growth target (~5,000 events/s) are well within Redis Streams' capacity. Kafka's disk-backed throughput advantage (hundreds of thousands of messages/s) is unnecessary at our scale and growth horizon.

3. **Consumer Groups and Ordering**: Redis Streams provides native consumer groups (`XREADGROUP`, `XCLAIM`) that distribute work across multiple workers and support explicit acknowledgment with automatic delivery of unacknowledged messages to other consumers. Ordering is preserved within a single stream, which we can shard by notification type (e.g., `stream:billing`, `stream:general`) to parallelize while maintaining per-type ordering.

4. **Message Retention**: Streams support capped lengths (`MAXLEN`) and time-based trimming. For our use case—an async work queue with retry—retention need only cover the duration of backoff retries (hours to days), not long-term log storage. Redis AOF persistence ensures messages survive process restarts. Memory-bound retention is acceptable because notifications are ephemeral, not audit logs.

5. **Exactly-Once for Billing**: Redis Streams provides at-least-once delivery by default. To achieve exactly-once for billing notifications, we will implement application-level idempotency: each billing notification carries a deterministic idempotency key (e.g., `billing:{user_id}:{event_type}:{timestamp_day}`). Consumers atomically check and set this key in Redis (or PostgreSQL) before processing. This is a proven, lightweight pattern that avoids the complexity of Kafka's transactional producer API and two-phase commit semantics.

6. **Strategic Fit for WebSocket Push**: Our roadmap includes real-time WebSocket notifications within two quarters. Redis already supports native pub/sub (`PUBLISH`/`SUBSCRIBE`) alongside Streams, giving us a unified platform for both durable queuing and real-time fan-out without introducing a third system.

7. **Cost**: Using existing Redis capacity (or adding a modest AWS ElastiCache or EC2 instance) fits our modest budget. Self-hosted Kafka would require at least 3 broker instances for fault tolerance plus monitoring overhead, while managed MSK or Confluent Cloud would strain our budget.

## Consequences

### Pros

- **Rapid migration**: Existing Redis expertise and infrastructure allow us to meet the 2-week delivery deadline.
- **Reduced operational surface**: One less technology to operate, monitor, and secure. The team uses a single operational playbook.
- **Unified real-time architecture**: Redis Streams (durable queueing) and Redis Pub/Sub (WebSocket fan-out) coexist in one system, reducing future integration complexity.
- **Sufficient headroom**: 10x growth remains comfortably within Redis performance envelope.
- **Incremental adoption**: We can migrate notification types one at a time (e.g., billing first, then general webhooks), reducing risk.

### Cons

- **Memory-bound retention**: Total stream retention is capped by available RAM. If we misconfigure `MAXLEN` or experience a prolonged consumer outage, we risk dropping messages. Mitigation: aggressive monitoring, conservative `MAXLEN` values, and dead-lettering to PostgreSQL for critical events after max retries.
- **No native exactly-once semantics**: Unlike Kafka's idempotent producers and transactions API, Redis Streams relies on application-level deduplication. This shifts correctness responsibility to our consumer code and requires careful idempotency key design.
- **Simpler consumer rebalancing**: Redis consumer group rebalancing is less sophisticated than Kafka's partition assignment protocol. Rapid worker scaling or redeployments can cause temporary message duplication. Mitigation: idempotent consumers and gradual rollouts.
- **Limited ecosystem**: Fewer mature stream processing frameworks and connectors compared to Kafka. Complex event processing or stream-to-data-warehouse pipelines would require custom code.

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the industry-standard for high-throughput, durable event streaming and offers native exactly-once semantics through idempotent producers and transactions. Its disk-based log provides near-unbounded retention, and consumer groups offer robust partition-based parallelism and rebalancing.

However, we rejected Kafka because:

- **Operational complexity exceeds team capacity**: Running a production Kafka cluster (3+ brokers, replication tuning, partition strategy, monitoring consumer lag, managing ISR sets, and KRaft metadata quorum) demands infrastructure expertise we do not have. Without a dedicated infrastructure engineer, a self-managed cluster is a high risk of future incidents.
- **Setup exceeds 2-week window**: A production-ready Kafka deployment, including client library integration, producer/consumer configuration, and operational runbooks, cannot be done safely in two weeks by a team with no prior experience.
- **Budget constraints**: Managed options (Confluent Cloud, AWS MSK) are not viable at scale today. Self-hosting on EC2 incurs compute and storage costs significantly higher than adding Redis Streams capacity.
- **Overkill for current scale**: Kafka's primary advantage is throughput in the hundreds of thousands of messages per second and long-term log retention. Our peak of ~500 events/s and ephemeral notification queue requirements do not justify the operational overhead.

**Revisit criteria**: If we exceed 50,000 events/s sustained, require multi-year retention of notification events, or hire a dedicated infrastructure engineer, we will re-evaluate Kafka as a migration target.
