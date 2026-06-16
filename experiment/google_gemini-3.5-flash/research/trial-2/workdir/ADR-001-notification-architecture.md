# ADR-001: Notification Subsystem Architecture

- **Title**: Notification Subsystem Architecture: Redis Streams vs. Apache Kafka
- **Status**: Accepted
- **Date**: 2026-06-16
- **Deciders**: Zaruba (Lead Architect)
- **Context tags**: notification, async, queue, messaging, redis, kafka

---

## Context

Our SaaS project management platform is experiencing significant performance degradation and reliability issues due to our current synchronous notification architecture. With 85,000 monthly active users (MAU), ~2M monthly task creations, and a peak throughput of ~500 requests per second (req/s), handling notifications (emails and webhooks) inside the HTTP request cycle has resulted in:
1. **High Latency & Timeouts**: Average request latency is 800ms, spiking to over 8 seconds during peak hours.
2. **Data Loss (Silent Failures)**: No retry mechanism or dead-letter queue (DLQ) exists; down email providers or webhook endpoints result in permanently lost notifications.
3. **Cascading System Failures**: Slow webhook responses have exhausted HTTP connection pools twice this year, taking down core, unrelated platform features.
4. **Weak Delivery Guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") have no delivery guarantees, despite requiring at-least-once delivery and exactly-once processing.

### Scaling Target
To handle a projected 10x traffic growth (reaching peak rates of ~5,000 req/s) and support real-time WebSocket push notifications within 2 quarters, we must transition to an asynchronous notification subsystem. The new architecture must support:
- Loose decoupling of notifications from HTTP request cycles.
- Reliable queueing with support for exponential backoff and retries.
- Guaranteed at-least-once delivery for billing events, and end-to-end exactly-once semantics where feasible.

### Key Constraints
- **Team Size**: A small team of 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure engineer**.
- **Existing Skills**: No Apache Kafka operational or development experience exists on the team today.
- **Timeline**: Must not require more than **2 weeks** of setup, integration, and migration work before delivering production value.
- **Infrastructure**: Redis is already successfully running in production for session storage and rate limiting.
- **Budget**: Modest budget constraints; managed Apache Kafka (e.g., Confluent Cloud) is cost-prohibitive at our scale today.

---

## Decision

We will use **Redis Streams** as the core backbone of our asynchronous notification subsystem, coupled with our existing PostgreSQL database and Redis-backed consumer workers.

### Justification

1. **Zero New Operational Overhead**: We already run and maintain Redis in production. Adopting Redis Streams adds zero new infrastructural components, avoids the need for dedicated DevOps/infrastructure support, and leverages our existing AWS Redis setup. This aligns perfectly with our 6-person team constraint.
2. **Under 2-Week Time-to-Value**: Because the team is already familiar with Redis and client libraries exist in Python (e.g., `redis-py`), we can deploy a production-ready asynchronous worker model within days. Setting up, securing, testing, and learning Apache Kafka from scratch would easily consume 4 to 8 weeks of engineering time, violating our 2-week delivery constraint.
3. **Performance & Scalability**: Redis Streams operates in-memory, delivering sub-millisecond latencies and easily handling tens of thousands of operations per second on a modest instance. Our 10x peak scaling target of ~5,000 req/s is well within the single-node capability of Redis Streams.
4. **Sufficient Consumer Group Features**: Redis Streams native consumer groups (via `XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, and `XCLAIM`) provide robust tools to distribute notifications across multiple Flask/Celery or custom consumer workers, track failures, and re-assign abandoned messages.
5. **Practical Exactly-Once Semantics**: Since billing-critical operations (such as "trial expired") run inside our Python monolith backed by PostgreSQL, we can implement exactly-once processing by utilizing a lightweight deduplication pattern. We will use a combination of unique idempotency keys stored in PostgreSQL (relying on ACID transactions) and a fast distributed lock or status check in Redis to ensure a notification is never processed twice. This approach is highly reliable and avoids the massive overhead of Kafka's transactional API, which still would not solve end-to-end exactly-once delivery to external email or webhook endpoints anyway.

---

## Consequences

### Pros (What We Gain)
- **Extremely Low Operational Complexity**: No new JVM-based clusters, ZooKeeper/KRaft setups, partition rebalancing, or disk management.
- **Rapid Time-to-Market**: Setup, integration, testing, and deployment can be achieved in less than one week.
- **Cost-Efficiency**: Reuses existing Redis infrastructure on AWS, requiring only modest vertical scaling of memory or a low-cost replica, fitting our modest budget.
- **Exceptional Latency**: In-memory storage guarantees minimal ingestion latency from the Python Flask monolith.
- **Rich Consumer Semantics**: Built-in support for message acknowledgment (`XACK`), pending message tracking (`XPENDING`), and claiming of dead consumer messages (`XCLAIM`) allows us to build reliable DLQs and retry mechanisms.

### Cons (What We Must Manage)
- **In-Memory Limitations**: Unlike Kafka's disk-backed append-only log, Redis Streams stores messages in-memory. A massive backup of unprocessed notifications could lead to Out-Of-Memory (OOM) errors. 
  - *Mitigation*: We will use the `MAXLEN` or `MINID` stream-trimming options (e.g., `XADD stream MAXLEN ~ 50000`) to cap stream sizes and persist acknowledged notification logs/audit trails to PostgreSQL for long-term historical records.
- **Data Persistence Risk**: Depending on Redis persistence configuration (AOF vs. RDB), there is a slight risk of losing in-flight notifications in a hard crash.
  - *Mitigation*: Configure Redis with Append-Only File (AOF) set to `appendfsync everysec` to bound maximum data loss to 1 second, which is highly acceptable for notifications.
- **No Automatic Cluster Partition Rebalancing**: Redis Streams does not automatically rebalance partitions among consumers in the way Kafka does.
  - *Mitigation*: Since our scale is highly manageable (~500 req/s scaling to ~5,000 req/s), we can statically configure consumer workers and handle failures manually or programmatically using `XCLAIM`.

---

## Alternatives Considered

### Apache Kafka

We rejected Apache Kafka for the following reasons:

- **Unjustifiable Operational Complexity**: Kafka requires significant effort to configure, secure, monitor, and scale. With only 6 engineers and no dedicated infrastructure engineer, managing ZooKeeper/KRaft metadata, tuning JVM garbage collection, configuring disk replication factors, and managing partition counts would create a massive operational bottleneck.
- **Violates Setup Constraints**: The team has zero Kafka experience. Training the team, designing a robust schema registry, setting up local development clusters, and deploying a reliable production cluster would take at least 4 to 6 weeks, far exceeding our 2-week time-to-value constraint.
- **Prohibitive Cost**: A managed Kafka cluster on Confluent Cloud or AWS MSK would run into thousands of dollars per month at our targeted scale. Self-hosting on EC2 would require a minimum of 3 brokers and 3 ZooKeeper/KRaft coordinators to maintain high availability, exceeding our modest budget.
- **Overkill for Target Throughput**: Kafka's architecture is optimized for ingest rates of millions of events per second. Our 10x target of 5,000 req/s is easily handled by Redis Streams without the massive CPU and storage overhead of Kafka.
- **Exactly-Once Illusion**: While Kafka supports transactional producers/consumers for exactly-once semantics within the Kafka boundary, this guarantee breaks the moment a notification worker calls an external, non-transactional HTTP endpoint (such as SendGrid or Stripe Webhooks). Since consumer-side idempotency is required anyway to achieve end-to-end exactly-once behavior, Kafka's transactional model provides no functional advantage over Redis Streams in our specific notification context.

*We would have chosen Apache Kafka if our throughput requirements were 100x higher (e.g., >50,000 req/s), if we had a dedicated DevOps/infrastructure team, or if we required long-term, multi-gigabyte message retention directly within the log broker.*
