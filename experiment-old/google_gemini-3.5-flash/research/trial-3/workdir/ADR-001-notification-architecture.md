# Title: ADR-001 - Choosing Redis Streams for the Notification Subsystem

## Status
Approved

## Context
Our SaaS project management platform is experiencing significant performance degradation and reliability issues due to its synchronous notification system. Currently, the notifications module (sending emails and executing webhooks) runs synchronously within our Python/Flask monolith's HTTP request cycle. Under our current load (85,000 monthly active users, ~2M tasks created/month, and a peak of ~500 req/s), this architecture has caused several severe production issues:
1. **Request Timeouts**: Sending notifications blocks the HTTP response, driving average latency to 800ms with spikes up to 8 seconds during peak hours.
2. **Silent Failures**: Down downstream email providers or webhook endpoints lead to silently dropped notifications with no retry mechanism or Dead Letter Queue (DLQ).
3. **Cascading Failures**: Connection pool exhaustion from slow webhook endpoints has twice taken down unrelated system features.
4. **No Delivery Guarantees**: Critical billing-related notifications (e.g., "payment failed", "trial expired") lack delivery guarantees.

### Scaling Target and Future Requirements
- **Decoupled Architecture**: Transition notification delivery to asynchronous processing.
- **Reliable Retries**: Support retry policies with exponential backoff and DLQ capabilities.
- **At-Least-Once Delivery**: Guarantee that all critical events are delivered at least once, aiming for exactly-once semantics where feasible (particularly for billing).
- **WebSocket Push Notifications**: Plan to introduce real-time WebSocket push notifications within 2 quarters.
- **10x Scale Goal**: Handle a 10x traffic growth (representing 5,000 peak req/s and ~20M tasks/month) without requiring a re-architecture.

### Constraints
- **Team Size**: A small team of 6 engineers (3 senior, 3 mid-level) with no dedicated DevOps or infrastructure engineer.
- **Technical Experience**: The team has zero experience operating or developing with Apache Kafka, but already operates Redis in production for session storage and rate limiting.
- **Timeline**: The solution must be production-ready and deliver value in under 2 weeks.
- **Budget**: Highly constrained; managed Kafka solutions (like Confluent Cloud at scale) are cost-prohibitive.
- **Infrastructure**: Hosted on AWS with PostgreSQL (primary + read replica) and a production Redis instance.

---

## Decision
We choose **Redis Streams** as the underlying message broker for our notification subsystem. We reject Apache Kafka for this architecture.

### Justification

1. **Operational Complexity and Team Alignment**:
   Operating a Kafka cluster requires substantial expertise in ZooKeeper/KRaft, JVM tuning, partition management, and network configuration. With a 6-person team and no dedicated infra engineer, adopting Kafka would introduce a massive operational burden. Redis Streams runs on our existing production Redis infrastructure, requiring zero new infrastructure provisioning, zero new monitoring setups, and no additional maintenance overhead.

2. **Time-to-Value (2-Week Constraint)**:
   A Kafka implementation—including security configurations (SASL/SSL), cluster setup, client library integration, and team training—would easily exceed our strict 2-week deadline. Redis Streams integrates seamlessly with our current Python/monolith architecture using existing, mature Redis client libraries (e.g., `redis-py`), allowing us to deploy a working async worker pool within days.

3. **Throughput at 10x Scale**:
   Our 10x scaling target requires handling a peak of 5,000 requests/second. Because Redis is an in-memory database, a single lightweight Redis instance can easily handle 100,000+ write operations per second with sub-millisecond latencies. Redis Streams will comfortably scale well beyond our 10x target with minimal CPU/RAM footprint.

4. **Exactly-Once Semantics (EOS) for Billing**:
   While Apache Kafka advertises "exactly-once semantics", this guarantee is strictly limited to transactional processing *within Kafka itself* (reading from Kafka, processing, and writing back to Kafka). Because our notification subsystem executes external network requests (sending emails via SendGrid/Mailgun or calling third-party webhooks), **neither Kafka nor Redis Streams can guarantee exactly-once delivery to the end system at the broker level**. 
   If a network hiccup occurs after the external provider processes the request but before they respond, a retry is mandatory, leading to duplicate delivery. 
   
   Therefore, exactly-once delivery for billing must be enforced at the **consumer level using the Idempotent Consumer Pattern**. We will implement this by assigning a unique, deterministic `notification_id` to each event and tracking processed IDs using a unique PostgreSQL constraint or a Redis-based distributed transaction lock. Since application-level deduplication is mandatory under both options, Kafka's internal EOS provides no additional benefit for our use case.

5. **WebSocket Compatibility**:
   Implementing real-time WebSockets within 2 quarters is highly straightforward with Redis. We can combine Redis Streams with Redis Pub/Sub to easily broadcast real-time updates to lightweight WebSocket server processes (such as a separate gevent/eventlet Flask server or a FastAPI instance) with low resource overhead and minimal connection footprint.

---

## Consequences

### Pros (Benefits)
- **Extremely Low Latency**: Message ingestion and retrieval occur with sub-millisecond latencies because Redis processes data entirely in-memory.
- **Low Operational Overhead**: Leverages our existing, production-proven Redis deployment. No new infrastructure monitoring, patch management, or log aggregation pipelines are required.
- **Rapid Implementation**: Minimal learning curve allows the entire team to be productive immediately, safely meeting the 2-week delivery target.
- **Robust Consumer Group Support**: Native Redis Stream commands (`XGROUP`, `XREADGROUP`, `XPENDING`, `XCLAIM`, `XACK`) provide powerful competing consumer capabilities, track in-flight messages, and support safe retries of failed tasks.
- **Cost Efficiency**: Marginal infrastructure cost is practically $0 since we can utilize our current AWS ElastiCache/Redis instance (or slightly upgrade its node size at a fraction of Kafka's cluster cost).

### Cons (Risks & Mitigations)

- **In-Memory Volatility and RAM Constraints**: 
  Unlike Kafka, which persists all messages to disk and supports infinite retention, Redis Streams are stored in-memory (RAM). Unbounded stream growth will lead to RAM exhaustion and potential system failure.
  * *Mitigation*: We will strictly use capped streams. Every message write (`XADD`) will append the `MAXLEN ~ 10000` parameter. This caps the stream length to approximately 10,000 active/recent messages per topic, automatically evicting oldest processed entries. For historical tracking and audit trails, PostgreSQL will remain our durable source of truth.
  
- **Lack of Automatic Consumer Rebalancing**:
  When scaling consumer workers up or down, Redis Streams does not automatically rebalance stream partitions among active consumers like Kafka's coordinator protocol does.
  * *Mitigation*: We will write an explicit worker monitoring routine. Active consumers will periodically query the Pending Entries List (PEL) via `XPENDING` to find messages that have been in-flight too long (e.g., > 30 seconds). They will then use `XCLAIM` to gracefully take ownership of and process those orphaned tasks, guaranteeing at-least-once processing even if a consumer container crashes.

- **Data Durability Concerns**:
  By default, Redis may lose up to 1 second of data if the instance crashes before memory is synced to disk.
  * *Mitigation*: We will ensure Redis Append-Only File (AOF) persistence is enabled with `appendfsync everysec` on our AWS Redis cluster. For billing notifications where even a 1-second data loss is undesirable, the database transaction that creates/updates a task in PostgreSQL will also record a pending notification record in a PostgreSQL `outbox` table. A background worker will read from this table and publish to Redis Streams, ensuring that the source of truth is always durable, transactional PostgreSQL database records.

---

## Alternatives Considered

### Apache Kafka

We thoroughly evaluated Apache Kafka as an alternative but rejected it for the following reasons:

- **Extreme Operational Complexity**: Kafka requires running a cluster of brokers and a consensus mechanism (ZooKeeper or KRaft). Managing, securing (SSL/SASL), monitoring, backing up, and configuring Kafka demands specialized knowledge. Our 6-person team cannot afford to spend time on cluster management at the expense of product features.
- **Violates Setup Timeline**: Setting up a production-ready, highly available Kafka cluster on AWS, configuring secure consumer/producer configurations, and rewriting code would take at least 4–6 weeks—well beyond our 2-week limit.
- **Prohibitive Cost**: Kafka is designed for high-scale, multi-gigabyte ingestion. Operating even a minimal high-availability Kafka cluster carries substantial minimum costs. Additionally, managed solutions like Confluent Cloud are cost-prohibitive given our modest budget.
- **Over-engineering**: Our 10x target peak of 5,000 req/s represents roughly 5–10 MB/s of payload traffic. Kafka is designed to handle gigabytes/second across hundreds of partitions. Introducing Kafka for this traffic profile is a classic case of unnecessary architectural over-engineering.
- **Complex Client Libraries**: Python client libraries for Kafka (such as `confluent-kafka` or `kafka-python`) are significantly more complex to write, test, and debug than the simple `redis-py` interface, introducing a steep learning curve for our mid-level engineers.
- **Illusion of Exactly-Once Semantics (EOS)**: While Kafka supports transactional producers/consumers, this only guarantees exactly-once processing *within Kafka itself* (reading from one topic, writing to another). For external side-effects (sending emails via a third-party API or executing webhooks), Kafka cannot guarantee exactly-once execution. Application-level idempotency is still mandatory. Therefore, Kafka's EOS does not solve our billing notification challenge out of the box.
