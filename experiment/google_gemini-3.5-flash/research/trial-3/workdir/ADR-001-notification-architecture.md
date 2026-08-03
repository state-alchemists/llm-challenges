# Title: ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform is experiencing performance and reliability degradation within its notification subsystem. 

### Metrics and Constraints
* **Current Volume**: 85,000 monthly active users generating ~2 million tasks per month. Peak traffic reaches ~500 requests per second (req/s) during business hours.
* **Future Target**: Must scale to handle 10x traffic growth (~5,000 req/s peak) without requiring a complete re-architecture.
* **Team Profile**: 6 engineers (3 senior, 3 mid-level) with zero dedicated infrastructure engineers. The team has existing production experience with Redis, but zero experience with Apache Kafka.
* **Timeline Constraint**: Setup, migration, and value delivery must be achieved within 2 weeks.
* **Budget Constraint**: Modest budget; managed Confluent Cloud is financially unviable at our projected scale.

### Current Architecture Problems
1. **Request Timeouts**: Notifications (emails/webhooks) are processed synchronously inside the Python/Flask HTTP request-response cycle, causing an average latency of 800ms and peak spikes of up to 8 seconds.
2. **Silent Failures**: The absence of retry mechanisms or Dead Letter Queues (DLQs) means notifications are permanently lost when third-party providers (e.g., SendGrid, webhook targets) are offline.
3. **Cascading Failures**: Slow webhook targets have exhausted the database and connection pools, leading to complete outages of unrelated platform features.
4. **Lack of Delivery Guarantees**: Critical billing-related notifications (such as "trial expired" or "payment failed") have no transactional delivery guarantees.

### Non-Negotiable System Requirements
* Decouple notification dispatching from the HTTP thread pool (asynchronous processing).
* Implement robust retry capabilities using exponential backoff.
* Guarantee at-least-once delivery for billing and high-priority notifications.
* Support exactly-once processing semantics for billing-critical events.
* Provide low-latency, real-time WebSocket push notifications within 2 quarters.

---

## Decision
We will adopt **Redis Streams** as the architectural foundation for our asynchronous notification subsystem. 

We reject Apache Kafka for this use case because its heavy operational footprint, steep learning curve, and high cost directly conflict with our 6-person team constraint and 2-week delivery deadline.

### Detailed Justification

1. **Leveraging Existing Infrastructure and Expertise**
   We already run Redis in production for session storage and rate limiting. The engineering team is comfortable with its deployment, backup, and monitoring model. Choosing Redis Streams avoids the operational tax of introducing, securing, and maintaining a completely new middleware layer.

2. **Compliance with the 2-Week Delivery Timeline**
   Using Redis Streams requires zero new infrastructure provisioning. The existing `redis-py` client library is already present in our Python/Flask monolith. The team can develop, test, and deploy the stream producers and consumer groups within days, comfortably meeting the 2-week constraint.

3. **Performance and Throughput at 10x Scale**
   At our 10x scaling target (~5,000 req/s), Redis Streams—which processes messages in-memory—will easily handle the throughput with sub-millisecond latencies. A single Redis instance can support tens of thousands of writes/reads per second, meaning we can achieve our scaling targets without clustering or partitioning complexities.

4. **Reliable Async Processing and Consumer Groups**
   Redis Streams provides robust Consumer Groups (`XGROUP`, `XREADGROUP`, `XPENDING`, `XCLAIM`, `XACK`). This enables us to run multiple concurrent notification workers in our Python environment. Consumer Groups ensure that messages are distributed across workers, and the pending entries list (PEL) guarantees at-least-once delivery by tracking unacknowledged messages. If a worker dies mid-processing, another worker can safely claim (`XCLAIM`) and retry the message.

5. **Strict Ordering Guarantees**
   Task notifications (e.g., "task updated" -> "task assigned" -> "task completed") must be processed in chronological order to prevent race conditions or confusing user experiences. Redis Streams natively enforces strict FIFO (First-In, First-Out) ordering within a stream because all messages are assigned a monotonically increasing ID (`<milliseconds>-<sequence>`). By dedicating streams strategically (such as one stream per user/task or utilizing single-stream processing per worker), we guarantee in-order delivery of related notifications. Kafka achieves ordering via partition keys, which would require us to design and maintain partition schemas; Redis Streams delivers the same ordering guarantees with far simpler stream key setups.

6. **Exactly-Once Semantics (EOS) via Application-Level Idempotency**
   Since notifications are sent to external networks (SMTP servers, customer webhook endpoints), network-level exactly-once delivery is physically impossible (due to the Two Generals' problem). Exactly-once semantics must be achieved via **at-least-once broker delivery** paired with **idempotent consumer processing**.
   We will implement this by:
   * Generating a unique `idempotency_key` (e.g., `event_id` or `invoice_id`) inside our Flask application when a billing event is triggered.
   * Writing this event to PostgreSQL first within the local business transaction.
   * Publishing the event with its key to Redis Streams.
   * Wrapping the consumer process in a PostgreSQL transaction that verifies and records the `idempotency_key` in a `processed_notifications` table using a `UNIQUE` constraint. If a duplicate message is delivered, the database constraint prevents duplicate sending, ensuring exactly-once processing.

7. **WebSockets Readiness**
   Redis is highly optimized for real-time pub/sub and streaming. The choice of Redis Streams perfectly positions the team to implement low-latency WebSocket push notifications within the planned 2 quarters by reusing the same Redis infrastructure.

---

## Consequences

### Positive (Pros)
* **Zero Operational Overhead**: No new cluster infrastructure to deploy, monitor, patch, or configure. No dedicated DevOps hires required.
* **Negligible Setup Cost**: Utilizes our existing production Redis cluster, staying 100% within our modest budget.
* **Rapid Time-to-Market**: Development, integration, and release can be finalized within the 2-week window.
* **Highly Responsive UI**: Offloading notification logic to background consumer threads reduces HTTP request latency from ~800ms to <20ms.
* **Elimination of Cascading Outages**: Thread isolation means failing third-party APIs can no longer exhaust database connection pools or take down the main HTTP application servers.

### Negative (Cons)
* **In-Memory Volatility & RAM Overhead**: Redis is an in-memory data structure store. Unbounded streams will eventually cause Redis to run out of memory (OOM). We must strictly enforce stream trimming using the `MAXLEN` option (e.g., `XADD stream MAXLEN ~ 10000 *`) or periodically trim streams via `XTRIM` to limit RAM consumption.
* **Potential Data Loss on Outages**: Redis persistence (RDB/AOF) is highly reliable but not fully synchronous by default (to maintain extreme performance). In the event of a catastrophic bare-metal node failure or un-persisted crash, some un-synced stream messages could be lost.
* **No Historical Replay**: Once messages are processed, acknowledged, and trimmed from the stream, they are permanently gone. Replaying history from weeks ago is not natively supported without archiving.

### Mitigation Strategies
* **Transactional Outbox Pattern**: For critical billing notifications, the Flask monolith will write the notification state directly to PostgreSQL as an "outbox" record during the HTTP transaction. A background publisher will poll this table and write to Redis Streams. This ensures that even if Redis suffers a total memory loss, the authoritative source of truth in PostgreSQL is preserved, allowing safe re-publishing.
* **Strict Memory Capping**: All stream append calls (`XADD`) must specify a reasonable `MAXLEN` limit (e.g., capped at 50,000 messages) to bound RAM growth.
* **Dead Letter Queues (DLQ)**: Consumers will track retry counts via Redis stream headers or database records. After 5 failed attempts, the consumer will ACK the message in the primary stream and publish it to a separate Redis DLQ stream (or record it in PostgreSQL) for manual operator intervention.

---

## Alternatives Considered

### Apache Kafka
We thoroughly evaluated Apache Kafka as the industry-standard event streaming platform. 

#### Why Rejected
* **Severe Operational Complexity**: Kafka requires a multi-broker setup, configuration of ZooKeeper or KRaft metadata layers, deep understanding of partition replication, JVM tuning, and extensive disk space provisioning. With only 6 engineers and no dedicated infrastructure engineer, self-hosting Kafka is an unacceptable operational risk that would distract from building product value.
* **Extreme Setup and Migration Overhead**: Establishing Kafka clusters, writing local Docker Compose setups, learning the complex Kafka API, configuring client libraries, and establishing monitoring/backup procedures would take several weeks or months, easily violating our non-negotiable 2-week delivery constraint.
* **Prohibitive Budget Constraints**: Managed alternatives like Confluent Cloud or AWS MSK are highly expensive at scale and would severely breach our modest budget limits.
* **Over-Engineering for Our Scale**: Kafka is built to handle millions of events per second across distributed clusters. Our projected peak scale of 5,000 req/s is well within the capabilities of a single-node in-memory Redis instance. Using Kafka would introduce massive, unnecessary complexity for a problem easily solved by Redis.
