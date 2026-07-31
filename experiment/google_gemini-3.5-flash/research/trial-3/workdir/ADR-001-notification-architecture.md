# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform is experiencing critical performance and reliability issues in its notification subsystem. Currently, the Python/Flask monolith sends email and webhook notifications synchronously within the HTTP request cycle. With 85,000 monthly active users and ~2 million tasks created per month (peak traffic of ~500 req/s), this synchronous design has led to:
1. **Severe Latency and Timeouts**: Sending notifications blocks HTTP responses, leading to an average latency of 800ms and spikes up to 8s during peak hours.
2. **Reliability and Silent Failures**: Transient network issues or downtime of downstream email providers and webhook endpoints cause notifications to be silently dropped, as there are no retry mechanisms or Dead-Letter Queues (DLQs).
3. **Cascading Failures**: Slow webhook targets have repeatedly exhausted our database connection pools, leading to platform-wide outages of unrelated features.
4. **No Delivery Guarantees**: Billing-critical events (such as trial expiration or payment failures) are processed with zero delivery guarantees, risking critical revenue leakages.

### Scaling Target
To support future growth and improve product capabilities, our architecture must evolve to:
- Decouple the notifications module from the HTTP request cycle (asynchronous processing).
- Support automatic retries with exponential backoff and DLQ routing.
- Guarantee at-least-once delivery for billing events, and achieve exactly-once processing where feasible.
- Power real-time WebSocket push notifications within the next 2 quarters.
- Scale to handle a 10x traffic increase (~5,000 req/s at peak, ~20 million tasks/month) without needing another structural re-architecture.

### Constraints
- **Team Size**: Only 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure or DevOps engineer. Minimizing operational overhead is paramount.
- **Timeline**: The solution must be implemented, tested, and delivering business value within 2 weeks.
- **Budget**: Modest budget; high-cost managed services (such as Confluent Cloud at scale) are not financially viable at this stage.
- **Technology Stack**: The current architecture uses a Python/Flask monolith, a PostgreSQL database (1 primary, 1 read replica), and a Redis instance used for session storage and rate-limiting. There is zero Kafka experience on the team.

---

## Decision
We will use **Redis Streams** as the backbone for our asynchronous notification subsystem. 

We reject **Apache Kafka** due to its prohibitive operational complexity, high cost, and long implementation cycle, which directly conflict with our 2-week time constraint and 6-person team size.

### Rationale and Technical Justification

#### 1. Low Operational Complexity and Team Familiarity
We already run and maintain Redis in our production environment for session management and rate limiting. Choosing Redis Streams introduces zero new infrastructure components. Our 6-person team does not have a dedicated DevOps engineer, meaning any new complex technology like Kafka would impose a continuous operational tax on our senior developers. Reusing Redis eliminates the steep learning curve, new monitoring configurations, and provisioning pipelines.

#### 2. Throughput & Scalability
While Apache Kafka is famous for handling millions of messages per second, our 10x scaling target requires handling peak volumes of 5,000 requests per second. Redis Streams, running entirely in-memory, easily achieves throughputs exceeding 100,000 write/read operations per second per node under standard workloads. A single Redis node or highly available Redis Sentinel/Cluster setup can handle our 10x peak traffic with sub-millisecond latencies, making its performance more than sufficient for our requirements.

#### 3. Strict Ordering Guarantees
Redis Streams guarantees strict FIFO ordering within a stream. Each entry appended via `XADD` is assigned a unique, monotonically increasing message ID composed of a millisecond timestamp and a sequence number (e.g., `1518091653459-0`). This ensures that task updates and status transitions are processed in the exact order they occurred, avoiding race conditions (such as sending a "Task Completed" email before "Task Created").

#### 4. Robust Consumer Groups
Redis Streams natively supports consumer groups (`XGROUP`, `XREADGROUP`). This allows us to scale out our Python background worker processes horizontally. Multiple workers can safely divide the notification load without message duplication. 
Crucially, Redis Streams maintains a **Pending Entries List (PEL)** per consumer group via the `XPENDING` and `XCLAIM` commands. If a worker dies mid-processing or an external API call hangs, the message remains in the PEL and can be claimed by another healthy worker after a timeout, ensuring that no message is lost.

#### 5. Pragmatic Exactly-Once Semantics (EOS)
Neither Kafka nor Redis Streams can natively guarantee exactly-once delivery when interacting with external networks (such as sending third-party emails via SendGrid or hitting custom webhook endpoints), because an API call can succeed while its network acknowledgment fails. 
True exactly-once processing is an end-to-end requirement. We will achieve it using the **Idempotent Consumer** pattern:
- Redis Streams provides **at-least-once delivery** guarantees through explicit acknowledgments (`XACK`).
- The Python consumers will leverage our existing **PostgreSQL** database to enforce deduplication. We will store a unique notification hash or ID in a deduplication table with a `UNIQUE` constraint (or execute the status check and write inside a database transaction). If a message is redelivered, the database constraint or transaction check will silently discard the duplicate, achieving exactly-once execution.

#### 6. Time-to-Value and Budget
Implementing Redis Streams requires no new AWS resource provisioning, zero licensing costs, and minimal setup. A standard Python consumer group loop using `redis-py` can be written, unit-tested, and integrated into our monolith within days, fitting comfortably inside our 2-week deadline. It avoids the thousands of dollars per month associated with managed Confluent Cloud or Amazon MSK.

#### 7. Readily Extensible to WebSockets
Our roadmap requires real-time WebSocket push notifications within 2 quarters. Redis features built-in Pub/Sub alongside Streams. We can seamlessly use Redis Pub/Sub to broadcast real-time events to our WebSocket servers, avoiding the need to add another broker (like RabbitMQ) when that phase begins.

---

## Consequences

### Positive
* **Rapid Delivery**: The 2-week implementation timeline is highly achievable, allowing us to solve the request latency and cascading failure issues immediately.
* **Low Maintenance Overhead**: No additional infrastructure monitoring, JVM tuning, ZooKeeper/KRaft maintenance, or security patching is required.
* **Resource Efficiency**: In-memory speeds yield ultra-low latency (sub-millisecond) queueing and processing.
* **Monolithic Alignment**: Integrates naturally into our Python/Flask monolith using mature Python libraries (`redis` or task-runners like `Huey` / `Celery` backed by Redis).

### Negative / Trade-offs
* **In-Memory Limitations**: Unlike Kafka, which persists data to disk indefinitely, Redis keeps streams in memory. If our consumers fail and fall behind significantly, Redis memory usage could spike, risking Out-Of-Memory (OOM) errors.
  * *Mitigation*: We will cap our streams using the `MAXLEN ~ 10000` option on `XADD` to automatically evict old messages once they are processed.
* **Durability Trade-off**: In the event of a catastrophic dual-node Redis crash, unacknowledged messages could be lost.
  * *Mitigation*: We will configure Redis persistence with Append-Only File (AOF) set to `appendfsync everysec`. Additionally, our PostgreSQL database remains the absolute source of truth; any critical billing event will be logged in PostgreSQL first before appending to Redis Streams. If Redis experiences a catastrophic failure, we can rebuild the pending queue by scanning PostgreSQL.
* **Consumer-Side Complexity for EOS**: Exactly-once processing is not out-of-the-box.
  * *Mitigation*: Developers must explicitly handle deduplication logic using PostgreSQL unique constraints for billing notifications.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
* **Overwhelming Operational Tax**: Operating Kafka requires managing brokers, partitions, replication factors, and either ZooKeeper or KRaft. For a 6-person team with no dedicated infrastructure engineer, this represents an unacceptable maintenance burden.
* **High Cost**: Managed Kafka via AWS MSK or Confluent Cloud carries significant base costs that do not scale down nicely for a modest budget. Self-hosting is extremely risky and prone to configuration-induced data loss.
* **Steep Learning Curve**: With zero Kafka experience on the team, setup, configuration, and integration would easily exceed the 2-week timeline, stalling product delivery.
* **Over-Engineering**: Kafka's high durability and multi-terabyte log retention are unnecessary for transient notification delivery, where messages are typically discarded or archived to a relational database immediately after delivery.
