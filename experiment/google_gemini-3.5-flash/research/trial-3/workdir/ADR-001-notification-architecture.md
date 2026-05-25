# ADR-001: Notification Subsystem Architecture

- **Status**: Proposed
- **Context**:
  The notifications module (emails and webhooks for task updates, assignments, and completions) is currently handled synchronously inside our Python/Flask monolith request cycle. With 85,000 MAU, ~2M tasks/month, and a peak throughput of ~500 req/s during business hours, this synchronous flow is causing severe production issues:
  1. **Request Timeouts**: Blokcing HTTP threads during notification dispatch drives average latency to 800ms, with spikes up to 8s during peak hours.
  2. **Silent Failures**: Down stream email provider or webhook endpoint failures result in silently dropped notifications without retries or Dead-Letter Queues (DLQs).
  3. **Cascading Failures**: Connection pool exhaustion due to slow webhooks has caused two major platform outages this year.
  4. **No Delivery Guarantees**: Billing-critical events (e.g., "trial expired", "payment failed") are sent without at-least-once or exactly-once delivery guarantees.

  **Scaling Target & Constraints**:
  - We must decouple notifications to run asynchronously, support exponential backoff retries, and handle a 10x traffic increase (up to 5,000 req/s, translating to an estimated peak of 15,000 notifications/s).
  - We must add WebSocket real-time push capabilities within 2 quarters.
  - Engineering team consists of only 6 people (3 senior, 3 mid-level) with *no dedicated infrastructure engineer* and *zero Apache Kafka experience*.
  - We must deliver value within 2 weeks.
  - The budget is modest; high-cost solutions like fully managed Confluent Cloud are off the table.
  - Exactly-once semantics must be maintained for billing-critical notifications.

- **Decision**:
  We will use **Redis Streams** as the message broker for our decoupled, asynchronous notification subsystem, combined with application-layer idempotent consumers to guarantee exactly-once processing for billing notifications.

  **Justification**:
  1. **Operational Simplicity & Overhead**: We already run and maintain Redis in production for session storage and rate limiting. Adapting it for Redis Streams introduces zero new infrastructure setup, zero additional license/hosting cost, and requires no specialized infrastructure engineer.
  2. **Time to Market**: The 6-person team can deliver value well within the 2-week constraint because the team is already familiar with Redis APIs and operations. 
  3. **Performance and Scaling**: Redis is extremely high-throughput. A single Redis instance can process upwards of 100,000 operations per second. Even under our 10x target of 5,000 req/s (15,000 notifications/s), Redis Streams will handle the load with microsecond latencies on minimal, cost-effective hardware.
  4. **Consumer Groups**: Redis Streams supports native consumer groups (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`). This allows us to scale out Flask background worker threads/processes to process notifications concurrently, manage message acknowledgments, track pending tasks, and recover failed/crashed consumers safely.
  5. **Deduplication and Exactly-Once Semantics (EOS)**: True end-to-end exactly-once delivery over the network (e.g., SMTP or webhook HTTP requests) is mathematically impossible because external APIs do not participate in distributed transactions (two-phase commit). Therefore, exactly-once processing must be solved at the application boundary via:
     - **At-least-once delivery** provided by Redis Streams' acknowledgment (`XACK`) and pending message recovery (`XCLAIM`).
     - **Consumer-side idempotence** achieved by using our existing Redis instance to store atomic, high-performance transaction deduplication keys (e.g., `processed:notification:<uuid>` with a 24-hour TTL) or using PostgreSQL's primary/unique key constraints inside database transactions.
  6. **WebSocket Compatibility**: Since Redis native Pub/Sub and Streams integrate seamlessly, implementing the real-time WebSocket push notifications next quarter will be highly straightforward using the same Redis infrastructure.

- **Consequences**:
  - **Pros**:
    - **Ultra-low Operational Complexity**: Zero new infrastructure elements to configure, provision, monitor, and scale. We leverage our existing AWS ElastiCache / Redis deployment.
    - **High Velocity**: Implementation can begin immediately and be completed within 1 week, allowing the remaining time for robust integration testing of the retry with exponential backoff mechanism.
    - **Minimal Cost**: Reusing our existing Redis setup results in negligible additional infrastructure expenses.
    - **Strong Cooperative Processing**: Native Redis Consumer Groups provide efficient worker load-balancing, offset tracking, and automated message re-claiming (`XCLAIM`) to prevent processing losses when worker nodes crash.
  - **Cons**:
    - **In-Memory Retention Constraints**: Redis is fundamentally an in-memory datastore. It does not support cheap, multi-terabyte persistent disk storage of historical messages. 
    - **Strict Memory Management Required**: To avoid running out of RAM (OOM errors), we must enforce strict stream trimming strategies using `MAXLEN ~ 100000` or `MINID` on `XADD` operations. Once messages are acknowledged and processed, they must be discarded from Redis, and long-term analytical histories must be archived in PostgreSQL or standard logs.
    - **Persistence Trade-Offs**: Redis persistence configurations (AOF/RDB) involve a trade-off between write throughput and data durability. To guarantee at-least-once delivery for critical events during a hard server crash, we must enable Append-Only File (AOF) with `appendfsync everysec`, which provides an upper bound of 1 second of data loss in extreme hardware failure scenarios.

- **Alternatives Considered**:
  - **Apache Kafka**:
    *Why Rejected*: Apache Kafka is a powerful event-streaming platform that offers native partition-level ordering, disk-backed infinite retention, mature consumer groups, and built-in cluster-wide transactional boundaries. However, Kafka was rejected due to:
    - **Extreme Operational Complexity**: Kafka requires a ZooKeeper or KRaft coordination cluster, deep JVM tuning, broker networking configuration, partition/replication balancing, and meticulous disk-capacity planning. Without a dedicated infrastructure engineer, self-hosting is a high-risk vector for catastrophic platform downtime.
    - **Skill Gap**: Our 6-person team has zero Kafka experience. Up-skilling the team and writing a robust producer/consumer implementation in Python (which requires wrapping the native C-library `librdkafka`) would take far longer than the 2-week delivery target.
    - **Cost Constraints**: Fully managed options like Confluent Cloud are too expensive for our modest budget, and self-hosting Kafka on multi-node AWS EC2 clusters to ensure high availability would dramatically increase our monthly cloud bill.
    - **Over-Engineering**: Kafka's massive scale and disk replayability properties are unnecessary for our transient task notification queues. Redis Streams easily satisfies our 10x peak throughput requirement (~15,000 msgs/s) on minimal operational resources.
