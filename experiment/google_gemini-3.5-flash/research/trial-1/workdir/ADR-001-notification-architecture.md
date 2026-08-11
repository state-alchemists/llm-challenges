# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform currently processes approximately 2 million tasks per month with 85,000 monthly active users. During business hours, we experience peak loads of ~500 requests per second. 

Our current architecture consists of a Python/Flask monolith (~50k LOC) backed by a PostgreSQL database (single primary and one read replica), 4 web servers behind an nginx load balancer hosted on AWS, and a Redis instance used for session storage and rate limiting.

Currently, notifications (emails and webhooks triggered by task updates, assignments, or completions) are sent synchronously within the HTTP request-response cycle. This has introduced critical issues:
1. **Request Timeouts**: Sending notifications blocks HTTP responses, leading to an average latency of 800ms with spikes up to 8 seconds during peak hours.
2. **Silent Failures**: Down external email providers or third-party webhook endpoints lead to silently dropped notifications with no retry mechanism or Dead-Letter Queue (DLQ).
3. **Cascading Failures**: Slow webhook targets have twice exhausted our database connection pools, causing cascading outages across unrelated platform features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") have no delivery guarantees, risking critical revenue leaks.

### Scaling Target & Constraints
We must decouple notifications from the HTTP request cycle, support retry with exponential backoff, ensure at-least-once delivery for billing events (with exactly-once processing where feasible), integrate real-time WebSocket push notifications within 2 quarters, and scale up to 10x traffic (peak ~5,000 req/s) without re-architecting.

The following constraints govern this decision:
- **Team Size**: A small engineering team of 6 people (3 senior, 3 mid-level) with **no dedicated infrastructure/DevOps engineer**.
- **Expertise**: **No Kafka experience** on the team today.
- **Timeline**: Must deliver business value within **2 weeks of setup and migration work**.
- **Budget**: Modest; we cannot afford managed enterprise Kafka (e.g., Confluent Cloud) at full scale today.
- **Existing Footprint**: We already run and maintain Redis in production for session storage and rate limiting.

---

## Decision
We will use **Redis Streams** to power our asynchronous notification subsystem, rejected Apache Kafka.

### Justification
Redis Streams provides the ideal balance of performance, low operational overhead, and quick time-to-value for our 6-person engineering team. We justify this choice through specific technical properties mapped to our constraints:

1. **Operational Complexity & Team Constraints**: 
   Managing an Apache Kafka cluster (or even KRaft/ZooKeeper, partition rebalancing, JVM optimization, and disk persistence models) represents an immense operational overhead. Since our team has zero Kafka experience and no dedicated infrastructure engineer, self-hosting Kafka is a substantial risk. On the other hand, we already run Redis in production. Choosing Redis Streams introduces zero new infrastructure components, eliminating deployment friction and allowing our team to easily meet the strict **2-week delivery timeline**.

2. **Throughput & Scalability**: 
   At 10x traffic growth, our peak web traffic will reach ~5,000 req/s. Even if every web request produces a notification event, Redis Streams—being an in-memory data structure—can easily handle tens of thousands of write/read operations per second on a single thread. It is more than capable of handling our projected 10x scaling target with negligible CPU and memory overhead, requiring no complex horizontal partitioning or clustering at our scale.

3. **Ordering Guarantees**: 
   Redis Streams maintains a strict, append-only log structure where messages are automatically assigned monotonically increasing, timestamp-based IDs. This guarantees strict chronological ordering of notification events, ensuring that sequential updates to the same task (e.g., "Created" -> "Assigned" -> "Completed") are processed in the correct order.

4. **Consumer Groups**: 
   Redis Streams supports native Consumer Groups through commands like `XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, and `XCLAIM`. This allows multiple concurrent background Python worker processes to act as competing consumers, scaling our processing capacity horizontally as traffic grows while ensuring each notification is processed by only one worker.

5. **Exactly-Once Semantics (EOS) for Billing**: 
   Our billing-critical notifications require exactly-once processing. While Kafka supports transactional exactly-once semantics within its broker boundaries, this guarantee does not extend to external side-effects like invoking third-party email APIs (e.g., SendGrid) or sending webhooks. If a worker crashes immediately after sending an email but before committing its offset, the email will be re-sent regardless of the broker used.
   To achieve true exactly-once semantics, we must implement an **idempotent consumer** pattern at the application level. By leveraging our existing PostgreSQL database, we can store a unique transaction/event ID in a deduplication table with a `UNIQUE` constraint, wrapped in a database transaction. Combined with the at-least-once delivery guarantees of Redis Streams (using `XACK` and claiming timed-out pending messages via `XPENDING`/`XCLAIM`), this application-level deduplication reliably guarantees exactly-once processing for billing events.

6. **Budget**: 
   Reusing our existing Redis deployment or scaling up a small Redis instance is highly cost-effective and fits perfectly within our modest budget, whereas managed Kafka offerings would introduce high, recurring monthly costs.

---

## Consequences

### Positive (Pros)
- **Extremely Low Time-to-Value**: Setup and migration can be completed in a few days, leaving ample time within our 2-week limit to implement retries and database integrations.
- **Zero New Infrastructure**: We avoid the overhead of provisioning, securing, monitoring, and patching a new database/broker platform.
- **Developer Familiarity**: The team already understands Redis, ensuring high velocity and minimal friction when implementing producer/consumer code.
- **Low Latency**: Redis's in-memory nature ensures sub-millisecond write and read latencies.
- **WebSocket Readiness**: Redis is highly optimized for real-time pub/sub and push patterns, which provides a natural transition to the WebSocket notifications planned for Q2.

### Negative (Cons)
- **In-Memory Limitations & Volatility**: Unlike Kafka, which persists data to disk indefinitely, Redis Streams resides in memory. If our background workers experience a prolonged outage while notifications continue to accumulate, Redis could run out of memory (OOM), crashing the cache.
  - *Mitigation*: We must strictly bound stream length using capped streams (`XADD ... MAXLEN ~ 100000`) or periodic trimming (`XTRIM`). This bounds memory consumption to a predictable maximum.
- **Ephemeral Retention**: Redis Streams are not designed for long-term historical message storage or offset replays over weeks of historical data.
  - *Mitigation*: Redis Streams will only be used as a transient transport medium. Once a message is acknowledged (`XACK`), it is considered consumed. Any long-term audit trail of notifications must be written to our persistent PostgreSQL database.
- **Manual Pending Message Reclamation**: Unlike Kafka’s automated partition rebalancing, if a Redis consumer dies, its pending messages remain locked in its Pending Entries List (PEL). 
  - *Mitigation*: We must implement a background sweeper thread in our worker pool that periodically calls `XPENDING` and uses `XCLAIM` to reclaim and re-process messages that have been stalled beyond a visibility timeout (e.g., 30 seconds).

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
- **Excessive Operational Overhead**: Kafka requires running and monitoring multiple brokers, JVM fine-tuning, disk space management, and configuring Apache ZooKeeper or KRaft. For a team of 6 with no dedicated infra engineer, this is an unacceptable operational risk that would distract from core product development.
- **Violates Setup Constraints**: Deploying a production-grade, highly available Kafka cluster, writing integration tests, and ensuring proper partition schemas would easily take more than 2 weeks, failing our primary delivery constraint.
- **High Financial Cost**: Managed Kafka solutions like Confluent Cloud or AWS MSK are highly cost-prohibitive for our modest budget, especially at our 10x scale target.
- **Overkill for Our Load**: While Kafka’s throughput capacity is unmatched, our 10x scaling target peak of ~5,000 transactions/second is extremely modest and well within the processing boundaries of a single Redis instance. Kafka's heavy architectural footprint is unnecessary for our scaling requirements.
