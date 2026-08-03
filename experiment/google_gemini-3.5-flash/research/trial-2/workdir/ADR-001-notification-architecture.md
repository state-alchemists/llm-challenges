# Architecture Decision Record (ADR) 001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform has outgrown its synchronous notification module, which currently sends emails and webhooks synchronously during the HTTP request cycle. With 85,000 monthly active users, ~2M tasks created per month, and peak traffic of ~500 req/s, this synchronous approach has introduced critical failures:
1. **Request timeouts**: Sending notifications blocks the response. Latency averages 800ms and spikes to 8s during peak hours.
2. **Silent failures**: If email or webhook endpoints are down, notifications are silently dropped without any retry mechanism or dead-letter queue.
3. **Cascading failures**: Slow third-party webhook endpoints have twice caused connection pool exhaustion, taking down unrelated features.
4. **Lack of delivery guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") have no at-least-once or exactly-once guarantees.

### Scaling Target
To support a 10x traffic growth target without re-architecting (up to 5,000 req/s peak and ~20M tasks/month), we must:
- Decouple notifications from the HTTP request cycle via asynchronous event processing.
- Support retry mechanisms with exponential backoff.
- Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- Add real-time WebSocket push notifications within 2 quarters.
- Deliver value with less than 2 weeks of setup/migration work.

### Constraints
- **Team**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure/DevOps engineer.
- **Experience**: Zero Apache Kafka experience on the team.
- **Budget**: Modest budget; cannot afford managed services like Confluent Cloud at scale.
- **Existing Infrastructure**: Redis is already running in production for session storage and rate limiting.

---

## Decision
We will use **Redis Streams** as the messaging backbone for our notification subsystem.

### Justification

1. **Operational Complexity and Team Size**:
   With only 6 engineers and no dedicated infrastructure engineer, self-hosting Apache Kafka is an unacceptable operational risk. Kafka requires managing JVM tuning, disk provisioning, broker replication, and coordination nodes (ZooKeeper or KRaft). In contrast, Redis is already running in our production environment. Leveraging Redis Streams requires zero additional infrastructure setup, zero new monitoring tools, and zero learning curve for basic operations, fitting perfectly within our strict **2-week delivery window**.

2. **Throughput and Latency**:
   Our peak traffic of 500 req/s (scaling to 5,000 req/s under 10x growth) is trivial for Redis Streams. Redis is memory-backed and can handle upwards of 50,000+ operations/second per node with sub-millisecond latencies. It easily handles our projected 10x growth target without requiring horizontal partitioning or clustering.

3. **Consumer Groups**:
   Redis Streams provides robust, native support for consumer groups via `XREADGROUP`, `XPENDING`, `XCLAIM`, and `XACK`. This allows us to scale worker processes (running alongside our Flask app servers) to process notifications concurrently. The Pending Entries List (PEL) tracks which worker has read which message but not yet acknowledged it, enabling redelivery/retry mechanisms if a worker crashes, eliminating silent failures.

4. **Exactly-Once Semantics (EOS)**:
   A major requirement is ensuring billing-critical notifications are processed exactly once. While Kafka supports transactional producers/consumers, this only guarantees exactly-once processing *within* Kafka (e.g., read from one Kafka topic and write to another). Because our notifications result in external network side effects (sending an email via SendGrid, firing an HTTP webhook to a user's server), **no message broker can natively guarantee end-to-end exactly-once execution**.
   
   To achieve exactly-once processing, we must implement application-level idempotency regardless of the broker. We will leverage an idempotent consumer design:
   - Messages are delivered at-least-once via Redis Streams.
   - Consumers process messages within a PostgreSQL database transaction, inserting a unique `notification_id` or `deduplication_key` into a `processed_notifications` table with a unique constraint.
   - If a duplicate message is received, the database unique constraint violation will safely abort the transaction before sending the external notification, or check-and-set logic will skip reprocessing.
   Redis Streams provides the necessary at-least-once delivery backbone to support this design.

5. **Message Retention and Memory Footprint**:
   Unlike Kafka’s disk-persistent log, Redis Streams are stored in memory. However, notifications are short-lived, transient messages. Once a notification is sent and acknowledged, we do not need to retain it in the stream. By using Redis’s native stream trimming (`XADD stream MAXLEN ~ 100000`), we can cap memory usage while keeping a rolling buffer of the last 100,000 notifications for debugging and short-term replay (consuming less than 50MB of RAM under peak load). This satisfies our storage needs without disk write bottlenecks.

6. **Real-time WebSocket Push**:
   Redis natively supports Pub/Sub and Streams. As we expand to real-time WebSocket push notifications next quarter, we can easily tap into our existing Redis instance to broadcast events to WebSocket servers, avoiding any additional message broker hops.

---

## Consequences

### Positive (Pros)
- **Zero Incremental Infrastructure**: No new software to install, configure, patch, or monitor. We leverage our existing production Redis instance.
- **Instant Developer Productivity**: The team is already familiar with Redis. Development can start on day one using standard Python libraries (such as `redis-py`), fitting easily within the 2-week constraint.
- **Sub-millisecond Latency**: Message queuing and retrieval are extremely fast, keeping latency minimal.
- **Predictable Budget**: No expensive Confluent Cloud subscription or large multi-node EC2 clusters required. Scale can be accommodated by scaling vertically (larger AWS ElastiCache instance) at a fraction of Kafka’s cost.
- **Robust Failure Recovery**: Consumer groups track failures and allow active workers to claim dead messages (`XCLAIM`), ensuring no notifications are lost.

### Negative (Cons)
- **In-Memory Limitations**: High-volume, unacknowledged messages can deplete Redis RAM if consumer workers crash for an extended period. We must implement alerts on stream size and Pending Entries List (PEL) depth to catch consumer blockages.
- **Lack of Long-Term Storage/Replay**: Unlike Kafka, which allows replaying weeks of historical messages from disk, Redis Streams is not meant for long-term storage. We must persist audit logs of sent notifications in PostgreSQL for auditing, rather than relying on the stream broker.
- **Manual Backoff Logic**: While Redis Streams supports tracking message delivery attempts via the PEL, implementing exponential backoff with jitter must be handled at the application/consumer layer (e.g., delaying acknowledgement and scheduling a retry message in a sorted set or database if a transient error occurs).

---

## Alternatives Considered

### Apache Kafka

We rejected Apache Kafka for the following reasons:

- **Prohibitive Operational Overhead**: A self-hosted Kafka cluster requires significant operational upkeep (managing JVMs, Zookeeper/KRaft, disk space, partition rebalancing, network tuning) which is too risky for a 6-person team with no dedicated infrastructure engineer.
- **High Financial Cost**: A managed Kafka solution (such as Confluent Cloud) is cost-prohibitive for our current budget at full scale.
- **Steep Learning Curve**: With no prior Kafka experience, the team would spend weeks mastering partition keys, offset management, consumer rebalances, and broker configurations, violating our **2-week time-to-value constraint**.
- **Overkill for Current and Future Scale**: Even at 10x growth, our peak is 5,000 req/s. Kafka is designed for hundreds of thousands to millions of writes per second. Its massive scale benefits do not justify its high operational complexity for our workload.
- **Misunderstood Exactly-Once Guarantee**: Kafka's transactional EOS is frequently cited as a reason to adopt it, but it cannot guarantee exactly-once side effects for external HTTP webhooks or email APIs. We would still have to write database-backed deduplication logic on the consumer side.
