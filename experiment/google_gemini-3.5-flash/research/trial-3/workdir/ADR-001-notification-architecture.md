# ADR-001: Choice of Notification Subsystem Engine

- **Status**: Proposed

## Context

We run a SaaS project management platform with 85,000 monthly active users (MAUs), approximately 2 million tasks created per month, and a peak traffic load of ~500 requests per second (req/s) during business hours (`system_context.md:6-8`). 

Our current architecture consists of:
* A Python/Flask monolith (~50k lines) (`system_context.md:12`).
* A PostgreSQL database with a single primary and one read replica (`system_context.md:13`).
* 4 web servers behind an AWS-hosted Nginx load balancer (`system_context.md:14`).
* Redis, currently used for session storage and rate limiting (`system_context.md:15`).

Currently, notifications (emails and webhooks triggered by task updates, assignments, or completions) are sent synchronously inside the HTTP request cycle (`system_context.md:16,20`). This setup has introduced severe issues:
1. **Request Timeouts**: Sending notifications blocks HTTP responses. Average latency is 800ms, spiking to 8s during peak hours (`system_context.md:22`).
2. **Silent Failures**: Downstream failures (e.g., mail provider or webhook endpoint outages) result in dropped notifications with no retry or Dead-Letter Queue (DLQ) mechanisms (`system_context.md:23`).
3. **Cascading Failures**: Slow downstream webhooks have caused PostgreSQL connection pool exhaustion twice this year, taking down unrelated features (`system_context.md:24`).
4. **No Delivery Guarantees**: Critical billing-related events (e.g., "trial expired", "payment failed") are treated the same as task events, with no delivery guarantees (`system_context.md:25`).

### Scaling Targets & Constraints

To resolve these issues, we must:
* Decouple notifications from the HTTP request cycle via asynchronous processing (`system_context.md:30`).
* Support retry mechanisms with exponential backoff (`system_context.md:31`).
* Guarantee at-least-once delivery for billing events, and maintain exactly-once semantics for billing notifications (`system_context.md:32,43`).
* Add real-time WebSocket push notifications within 2 quarters (`system_context.md:33`).
* Handle 10x traffic growth (scaling to ~5,000 peak req/s) without re-architecting (`system_context.md:34`).

We must achieve these goals under the following organizational constraints:
* **Team**: 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure engineer** and **no prior Kafka experience** (`system_context.md:38,40`).
* **Timeframe**: Must deliver value within a strict **2-week setup/migration limit** (`system_context.md:41`).
* **Budget**: Modest; cannot afford managed Apache Kafka (e.g., Confluent Cloud) at full scale (`system_context.md:42`).
* **Existing Infrastructure**: Redis is already operational in our production cluster (`system_context.md:39`).

---

## Decision

We will use **Redis Streams** as the underlying engine for our notification subsystem. 

### Justification

Redis Streams is the optimal choice because it fully satisfies our performance and operational requirements while aligning with our organizational constraints:

1. **Zero Operational Overhead**: We already run Redis in production (`system_context.md:39`). Implementing Redis Streams requires no new infrastructure, no additional licensing or hosting fees, and zero learning curve for managing a new database technology. This fits our 6-person team with no dedicated infrastructure engineer (`system_context.md:38`).
2. **Rapid Value Delivery**: With zero setup overhead, standard Python clients (such as `redis-py`), and simple command semantics, we can design, build, test, and deploy the new async notification flow well within the 2-week limit (`system_context.md:41`).
3. **Throughput Headroom**: While our peak load is 500 req/s (`system_context.md:8`) and our 10x target is 5,000 req/s (`system_context.md:34`), a single Redis instance easily handles over 100,000 operations per second. Redis Streams can easily ingest and distribute our target throughput.
4. **Robust Consumer Groups**: Redis Streams supports consumer groups via the `XGROUP` and `XREADGROUP` API families. This allows us to scale a pool of worker processes to consume notification tasks, distribute work evenly, track pending unacknowledged tasks (`XPENDING`), and reclaim failed consumer tasks (`XCLAIM`).
5. **Ordering Guarantees**: Messages appended to a Redis Stream are automatically assigned sequentially ordered, time-based IDs (e.g., `<millisecondsTime>-<sequenceNumber>`). This guarantees total ordering of notification triggers within each stream.
6. **Implementation of Exactly-Once Semantics (EOS)**: 
   In message-processing systems, network partitions make physical "exactly-once delivery" impossible. Exactly-once processing is achieved by combining **at-least-once delivery** with an **idempotent consumer pattern**.
   * **At-Least-Once Delivery**: Workers will consume messages using `XREADGROUP` and only call `XACK` (acknowledgement) after the notification has been successfully delivered (or reached the DLQ after maximum retries). Unacknowledged messages will remain in the Pending Entries List (PEL) and can be recovered using `XCLAIM`.
   * **Consumer Idempotency**: For billing-critical notifications, the consumer will execute its logic inside a **PostgreSQL database transaction**. When a worker processes a billing notification, it will write the unique Redis message ID to a PostgreSQL table named `processed_notifications` (which has a `UNIQUE` constraint on the `message_id` column). Because PostgreSQL is our single primary database, this write happens in the same transaction as application/billing state updates. If a message is redelivered due to a network hiccup or worker crash, the database transaction will roll back on the duplicate key violation, preventing duplicate processing.
7. **Simplicity of Real-Time WebSockets**: Redis Streams integrates naturally with WebSockets. Within the next 2 quarters, we can subscribe WebSocket server processes to Redis Streams or Pub/Sub channels to push real-time updates to connected clients with sub-millisecond latency, leveraging the exact same core infrastructure.

---

## Consequences

The selection of Redis Streams carries both positive and negative consequences:

### Pros (Benefits)
* **Immediate Deployment**: Development can start immediately using our existing production Redis cluster, ensuring we hit our 2-week deadline (`system_context.md:41`).
* **Minimal Resource Allocation**: No budget is diverted to new server provisioning or expensive enterprise managed queues (`system_context.md:42`).
* **Simple Client Architecture**: Writing Redis consumer code in Python is straightforward and has a very small codebase footprint compared to Kafka's complex client APIs.
* **Low Latency**: In-memory message processing guarantees sub-millisecond queuing latency, immediately eliminating our HTTP blocking problems.

### Cons (Drawbacks & Risks)
* **In-Memory Storage Constraints**: Since Redis is in-memory, keeping large backlogs of notifications could cause Out-of-Memory (OOM) errors. 
  * *Mitigation*: We will enforce proactive message trimming using the `MAXLEN ~ <size>` or `MINID` options on every `XADD` command, bounding our queue size to the last 100,000 messages (more than enough buffer for processing spikes). Historical logs of notifications will be archived in PostgreSQL, not Redis.
* **Lack of Native Event Replay**: Unlike disk-backed append-only logs (like Kafka), Redis Streams cannot easily store months of historical message logs for replay.
  * *Mitigation*: This is acceptable. Notifications are transient events. Once a notification is acknowledged and delivered (or logged as failed in our DB), we do not need to replay it from the queue. PostgreSQL remains our system of record.
* **No Multi-Resource Transactions**: Redis Streams cannot enlist in a distributed transaction with PostgreSQL.
  * *Mitigation*: Handled completely via the database-level idempotent consumer pattern described in the Decision section.

---

## Alternatives Considered

### Apache Kafka

We evaluated Apache Kafka as the alternative notification broker. Kafka is the industry standard for distributed event streaming and natively supports exactly-once transactional semantics (EOS), high durability, and massive scaling.

However, we rejected Apache Kafka for the following critical reasons:

1. **Extreme Operational Complexity**: Kafka requires significant effort to configure, secure, and maintain. Managing brokers, ZooKeeper/KRaft metadata controllers, JVM tuning, partition rebalancing, and client configurations requires deep expertise. With a 6-person team and **no dedicated infrastructure engineer**, self-hosting Kafka represents a massive operational liability.
2. **Prohibitive Budget Requirements**: We have a modest budget and cannot afford managed options like Confluent Cloud or AWS MSK at scale (`system_context.md:42`). Running a minimum high-availability Kafka cluster (at least 3 brokers and 3 ZooKeeper/KRaft nodes) on self-hosted EC2 instances is financially and operationally expensive.
3. **Severe Timeframe Violation**: Our team has **zero Kafka experience** (`system_context.md:40`). The learning curve for writing correct Kafka producers/consumers, setting up monitoring, and establishing deployment pipelines would make it impossible to deliver value within our strict **2-week limit** (`system_context.md:41`).
4. **Over-Engineering**: Kafka's primary strengths—such as infinite disk retention, partition-level horizontal scaling to millions of messages/sec, and distributed stream processing—are unnecessary for our scale. Our 10x target peak of 5,000 req/s represents a tiny fraction of Kafka's minimum capabilities, making it an unnecessary, high-cost architecture choice.
