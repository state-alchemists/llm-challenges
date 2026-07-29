# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, peak ~500 req/s) currently sends all notifications — emails, webhooks — synchronously inside the HTTP request cycle. This has led to four operational problems:

1. **Request timeouts**: Notification sending blocks responses. Average latency 800 ms, spiking to 8 s during peak hours.
2. **Silent failures**: Downstream email providers or webhook endpoints drop notifications with no retry or dead-letter queue.
3. **Cascading failures**: Two incidents this year where a slow webhook endpoint exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

We need to decouple notification production from delivery, add retry with exponential backoff, guarantee at-least-once delivery for billing events (exactly-once where feasible), prepare for WebSocket push notifications within two quarters, and handle 10x traffic growth without re-architecting.

Key constraints:
- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Existing stack**: Python/Flask monolith, PostgreSQL, Redis (session storage and rate limiting), AWS.
- **Time to value**: Must deliver working async processing within 2 weeks of starting migration.
- **Budget**: Modest — managed Confluent Cloud at production scale is not affordable today.
- **Semantics**: Billing notifications must not be duplicated or lost.

Two options are on the table: **Apache Kafka** and **Redis Streams**.

## Decision

**We choose Redis Streams.**

Redis Streams provides sufficient throughput, adequate ordering and consumer-group semantics, and — critically — it is already part of our production stack. The deciding factors are:

1. **Operational simplicity**: We run Redis today. Adding a stream key and consumer group requires zero new infrastructure, monitoring, or on-call rotation changes. Kafka would require provisioning a multi-broker cluster (KRaft or ZooKeeper), new monitoring, and operational runbooks — none of which our team has experience maintaining.

2. **Time to value**: A Redis Streams consumer can be implemented with the existing `redis-py` client in days. The Flask monolith already has a Redis connection pool. Kafka would require new client libraries (e.g., `confluent-kafka-python`), schema registry decisions, cluster provisioning, and team ramp-up — easily exceeding the 2-week constraint before any value is delivered.

3. **Throughput is not the bottleneck**: Our peak is ~500 req/s and the 10x target is ~5,000 msg/s. Redis Streams handles an order of magnitude beyond this on a single node. Kafka's strength — horizontal scaling to millions of messages per second across many partitions — is capacity we will not need in the foreseeable future.

4. **Exactly-once is achievable at the application layer**: Neither system provides true exactly-once for *external side effects* (sending an email, calling a webhook). Kafka's transactional producer guarantees exactly-once within the Kafka-to-Kafka path; the final delivery to an external system still requires application-level idempotency. Our approach — Redis Streams with at-least-once delivery (`XADD` → `XREADGROUP` → process → `XACK`), plus idempotency keys persisted in PostgreSQL for billing notifications — achieves the same effective guarantee without Kafka's operational overhead. The pending-entries list (PEL) gives us crash-recovery visibility into unacknowledged messages, enabling reliable retry.

5. **Budget**: Self-managed Kafka on AWS (3+ brokers, monitoring, storage) costs significantly more in compute and engineering time than scaling our existing ElastiCache or Redis instance. Managed Confluent Cloud at production throughput is outside our budget.

## Consequences

### Pros

- **Fast delivery**: Working async notification pipeline achievable within the 2-week window. Producer side is a `XADD` call replacing the current synchronous send; consumer side is a background worker with `XREADGROUP`.
- **No new infrastructure**: Redis is already in production, already monitored, already on-call. We add stream keys and consumer groups — not a new distributed system.
- **Sufficient performance**: Redis Streams comfortably handles our current peak (~500 msg/s) and 10x growth target (~5,000 msg/s). Benchmarks show single-node Redis sustaining 100K+ writes/s on modest hardware.
- **Consumer groups**: `XGROUP` and `XREADGROUP` provide partitioned consumption, load balancing across workers, and message ownership tracking via the pending-entries list — matching the core consumer-group model we need.
- **Retry and backoff**: The PEL (`XPENDING`) lets us detect stuck messages and re-deliver them, supporting exponential backoff at the application level.
- **Dead-letter path**: After N retries, messages move to a dead-letter stream, giving us visibility into permanently failed notifications — solving the silent-failure problem.
- **WebSocket readiness**: The same stream can be consumed by a WebSocket gateway service. Adding a new consumer group does not require infrastructure changes.

### Cons

- **Memory-bound retention**: Redis is primarily in-memory. Stream length must be bounded (`MAXLEN` or `XTRIM`), meaning messages are eventually evicted. For long-term audit trails, we must persist a copy to PostgreSQL before acknowledging — a pattern we should implement from day one.
- **Durability characteristics**: Redis AOF persistence writes to disk, but recovery semantics differ from Kafka's append-only commit log. Under a simultaneous Redis failure and consumer crash, a small window exists where a message is written but not yet fsynced. We mitigate this with: (a) `XADD` with synchronous AOF (`appendfsync always` or `everysec`), and (b) PostgreSQL idempotency records as the authoritative delivery state for billing notifications.
- **Less mature consumer groups**: Redis Streams consumer groups are functional but lack Kafka's ecosystem of tools (offset management UIs, partition rebalancing protocols, consumer lag monitoring dashboards). We will need lightweight internal tooling for monitoring PEL depth and consumer health.
- **Sharding is manual**: If throughput eventually exceeds a single Redis node, we must shard streams across keys or move to Redis Cluster. Kafka partitions are native. This is acceptable given our 10x growth target stays well within single-node capacity.
- **Future migration risk**: If the platform grows far beyond current projections (100x, not 10x), a migration to Kafka may become necessary. Choosing Redis Streams now means accepting that potential migration cost later. We accept this trade-off because: (a) the migration path is well-understood (dual-write, cut over consumer groups), and (b) optimizing for a 100x scenario today would violate the 2-week time-to-value constraint.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming. We rejected it for this decision point for the following reasons:

- **Operational overhead**: A production Kafka cluster requires 3+ brokers (for replication), monitoring (JMX metrics, consumer lag dashboards), and operational expertise for partition leadership elections, rebalances, and rollouts. Our team has no Kafka experience and no dedicated infrastructure engineer. The operational burden is disproportionate to our current scale.
- **Time to value**: Provisioning, configuring, and hardening a Kafka cluster — even using AWS MSK — takes weeks before the first message flows. Writing and testing producer/consumer code with `confluent-kafka-python`, deciding on a schema registry strategy, and establishing runbooks would not meet the 2-week constraint.
- **Cost**: AWS MSK (minimum 3 brokers, `kafka.t3.small`) starts at ~$300/month before storage and data transfer. Self-managed on EC2 is cheaper in raw compute but costs more in engineering time. Our budget is modest and already allocated.
- **Overcapacity**: Kafka's strengths — multi-partition ordering, replayable log retention over days/weeks, ecosystem integrations — solve problems we do not have. Our notification payloads are small, our throughput target is 5,000 msg/s, and our retention need is "until processed, then archive." Running Kafka for this would be operating a freight train to commute two blocks.

Kafka remains the right choice if the platform later needs multi-service event sourcing, real-time analytics pipelines, or audit logs with week-long replay windows. That is a future decision, not this one.

### Other alternatives briefly considered

- **PostgreSQL `SKIP LOCKED` / `SELECT FOR UPDATE`**: A queue table in our existing PostgreSQL would avoid new infrastructure entirely. However, it pollutes the OLTP database with queue semantics (table bloat, VACUUM pressure, lock contention under load) and provides no native consumer-group or pub/sub model for the upcoming WebSocket gateway. Suitable as a fallback, but not as the primary async transport.
- **RabbitMQ**: Feature-rich message broker with dead-letter exchanges and confirmed delivery. Rejected because it introduces a new piece of infrastructure with its own operational model, clustering requirements, and learning curve — similar to Kafka's drawback without Kafka's throughput advantage.
- **AWS SQS + SNS**: Fully managed, zero ops. Rejected because: (a) it locks us deeper into AWS for a core architectural component, (b) SQS does not support consumer groups natively (would need one queue per consumer type), and (c) SNS-to-SQS fan-out adds latency and complexity that Redis Streams avoids within our existing stack.