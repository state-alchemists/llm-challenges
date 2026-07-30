# ADR 001 — Selection of Redis Streams for Async Notification Subsystem

- **Status**: Accepted
- **Date**: 2026-07-30
- **Deciders**: Engineering Team (3 senior, 3 mid-level)
- **Context tags**: notifications, event-streaming, queue, redis, kafka

## Context

We run a SaaS project management platform with 85,000 monthly active users, processing approximately 2 million task creations per month and experiencing peak loads of ~500 req/s during business hours. 

Our current backend is a Python/Flask monolith (~50k lines of code) backed by PostgreSQL (single primary, one read replica). We already run Redis in production for session storage and rate limiting.

Currently, the notifications module dispatches emails and webhooks synchronously within the HTTP request cycle. This synchronous approach has caused several critical production issues as our user base has scaled:
1. **Request timeouts**: Sending notifications synchronously blocks responses, resulting in an average latency of 800ms and peak spikes up to 8s.
2. **Silent failures**: If a downstream email provider or webhook endpoint is down, the notification is silently dropped without retries or dead-letter queue (DLQ) containment.
3. **Cascading failures**: Slow third-party webhook endpoints have exhausted our Flask database connection pools twice this year, leading to cascading downtime across unrelated platform features.
4. **No delivery guarantees**: Critical billing events (e.g., "trial expired", "payment failed") are treated the same as regular updates, lacking any reliability or delivery guarantees.

### Scaling Target and Constraints

To resolve these issues, we need to transition to an asynchronous notification subsystem that decouples notification dispatch from the HTTP request cycle. Our system must support:
- Automatic retries with exponential backoff.
- At-least-once delivery guarantees for all billing-critical events, and exactly-once delivery where feasible.
- Real-time WebSocket push notifications to be added within 2 quarters.
- High horizontal scalability to handle 10x traffic growth (~5,000 req/s peak, or up to 10,000 notifications/s) without requiring a complete re-architecting of our queue setup.

However, we must work within the following strict constraints:
- **Team Size**: Only 6 engineers (3 senior, 3 mid-level), with no dedicated infrastructure or site reliability engineer (SRE).
- **Domain Expertise**: Zero experience with Apache Kafka on the team today.
- **Time to Value**: Setup and migration work must be completed in under 2 weeks.
- **Budget**: Modest. We cannot afford expensive enterprise solutions such as managed Confluent Cloud at our projected scale.

---

## Decision

We will use **Redis Streams** as the message broker and streaming engine for our asynchronous notification subsystem.

To support billing-critical exactly-once semantics and retry policies, we will pair Redis Streams with a **Transactional Outbox Pattern** in our primary PostgreSQL database and consumer-side **Idempotent Processing** utilizing Redis as a high-speed deduplication store.

---

## Rationale

Redis Streams is selected over Apache Kafka because it delivers the optimal balance of raw performance, architectural simplicity, and rapid time-to-value for our 6-person team.

Below is a detailed evaluation of both technologies across our key criteria:

### 1. Operational Complexity & Time to Value
* **Redis Streams**: **Extremely Low.** We already operate Redis in production for session management and rate limiting. Adopting Redis Streams adds no new infrastructure dependencies, port configurations, or monitoring agents to our stack. Python clients (such as `redis-py` or lightweight engines like `Huey`/`Celery`) are mature and easily integrated. Setup, development, and deployment can comfortably be completed within our strict 2-week timeline.
* **Apache Kafka**: **Prohibitively High.** Kafka requires managing a distributed cluster (using ZooKeeper or KRaft), tuning JVM memory settings, configuring replication factors, and managing consumer group partition offsets. Without a dedicated infrastructure engineer or pre-existing team expertise, managing self-hosted Kafka represents a substantial risk of catastrophic misconfiguration or data loss. Managed services (e.g., Confluent Cloud) are ruled out due to our budget.

### 2. Throughput & Scalability
* **Our Target**: Current peak is ~500 req/s (approx. 500-1,000 notifications/s). A 10x growth target requires supporting up to 10,000 notifications/s at peak.
* **Redis Streams**: A modest, single-node Redis instance can easily handle 50,000+ write/read operations per second. Redis Streams is fully capable of meeting our 10x scaling target out-of-the-box. If we eventually outgrow a single node, we can leverage Redis Cluster to partition streams horizontally across multiple master nodes.
* **Apache Kafka**: Capable of millions of writes per second. While Kafka's throughput ceiling is far higher, it is massive over-engineering for our scale.

### 3. Consumer Groups & Task Distribution
* **Redis Streams**: Supports consumer groups (`XGROUP`). Any active consumer worker in a group can request and process any available message. If a worker picks up a message and hangs (e.g., due to a slow, un-responsive third-party webhook), other workers continue processing the rest of the queue unimpeded. Stale or dead workers can be detected using `XPENDING` and their messages claimed by active workers using `XCLAIM`. This is highly beneficial for our workload, where third-party HTTP Latency is highly variable.
* **Apache Kafka**: Uses partition-bound consumer groups. A single partition can only be consumed by a single consumer instance in a group at any given time. If a consumer hangs while processing a slow webhook, the entire partition is blocked (head-of-line blocking), halting notifications for all other users mapped to that partition. To prevent this, we would have to implement complex custom thread pools inside our consumers, defeating the purpose of Kafka's built-in group coordinator.

### 4. Ordering Guarantees
* **Redis Streams**: Guarantees strict FIFO ordering of messages within a stream. Each entry is assigned a unique, monotonically increasing ID (e.g., `<timestamp>-<sequence>`). This guarantees that notification events (e.g., "Task Created" followed by "Task Completed") are processed by consumers in the exact sequence they occurred.
* **Apache Kafka**: Guarantees ordering *only per partition*. To maintain chronological ordering for a specific task's notifications, we would have to key our messages by `task_id` so they land on the same partition. While effective, it adds complexity to partition management and scaling.

### 5. Message Retention & Durability
* **Redis Streams**: Stored in-memory, backed by configurable persistence (RDB snapshots and AOF logs with `appendfsync everysec`). Old messages can be pruned automatically using the `MAXLEN` or `MINID` arguments on `XADD`. Since notifications are transient events that are quickly processed, acknowledged, and discarded, we do not require infinite or multi-week message replay capabilities. A bounded stream holding the last 100,000 events (roughly 1.5 to 3 hours of peak traffic) is more than sufficient for buffer absorption during consumer failures.
* **Apache Kafka**: Disk-bound, distributed commit log. Retains all messages up to a specified time or size limit. While highly durable, this persistent storage model is unnecessary for our ephemeral notification pipeline, where once an email or push notification is sent, it has no transactional value inside the message queue.

### 6. Exactly-Once Semantics (EOS)
* **The Reality**: No message broker (neither Kafka nor Redis Streams) can achieve end-to-end exactly-once delivery of external side-effects (such as sending an email via SendGrid or hitting an external webhook) on its own. If a worker successfully dispatches an email but crashes before acknowledging the message back to the broker, the message will be retried, resulting in a duplicate email.
* **Our Solution**: We will implement the **Transactional Outbox Pattern** alongside **Consumer Idempotency**. 
  1. When a task is updated in our PostgreSQL database, a `notification_outbox` record is written inside the *same database transaction*. This ensures that a notification is never queued unless the database change is successfully committed (at-least-once guarantee).
  2. A background publisher polls the outbox and writes events to **Redis Streams**.
  3. The consumer worker uses Redis to perform an atomic check-and-set of an idempotency key (e.g., `set notification:<id> "processing" EX 86400 NX`). If the key already exists, the consumer discards the duplicate message. This delivers robust, near-perfect "effectively exactly-once" delivery for critical billing events, regardless of the broker chosen.

---

## Consequences

### Positive (Pros)
- **Zero Infrastructure Overhead**: We leverage our existing Redis deployment. No new infrastructure provisioning, network configurations, or specialized cluster monitoring tools are required.
- **Immediate Time-to-Market**: The simplicity of Redis Streams enables our small team to deliver a working asynchronous prototype within days, leaving ample time for writing comprehensive tests and migration scripts within our 2-week window.
- **No Extra Costs**: Operating within our existing Redis memory footprint avoids any new licensing fees or managed cloud subscription costs, keeping our operational expenditures minimal.
- **Dynamic Parallelism**: Free consumers can pull tasks from the queue as fast as they can process them. Slow webhook endpoints or email server latency will not block other consumers, maximizing system throughput.
- **WebSocket Readiness**: Redis's high-speed pub/sub and blocking stream reads provide a natural, highly performant foundation for our upcoming real-time WebSocket push notification features in Q2.

### Negative (Cons)
- **Memory Consumption**: Because Redis is an in-memory database, unexpected consumer lag or downstream outages could cause messages to pile up, threatening to exhaust Redis RAM. We must mitigate this by:
  - Enforcing strict stream size limits using `MAXLEN ~ 100000` on stream writes.
  - Setting up aggressive alerting on Redis `used_memory` and consumer lag metrics.
- **Durability Trade-off**: In-memory storage is theoretically less durable than Kafka's disk-bound logs. In a worst-case catastrophic Redis crash, we could lose up to 1 second of un-acknowledged message data (due to `appendfsync everysec`). We accept this trade-off for notifications because:
  - Non-critical alerts (e.g., task updates) can tolerate minor loss.
  - Billing-critical alerts are durable on PostgreSQL in the `notification_outbox` table and can be safely re-published.
- **Manual Consumer Management**: Redis Streams does not automatically rebalance stream messages to active consumers when a consumer fails. We must write lightweight application-level polling logic that queries `XPENDING` and uses `XCLAIM` to re-assign stale, unacknowledged messages to healthy workers.

---

## Alternatives Considered

### Apache Kafka
- **Why Rejected**: Rejected due to prohibitive operational complexity, steep learning curve, high setup/running costs, and mismatch with our engineering constraints. For a team of 6 with no dedicated DevOps/SRE, Kafka would become a significant operational bottleneck, shifting valuable engineering hours away from product delivery toward infrastructure maintenance. Furthermore, Kafka’s partition-bound consumption pattern introduces a severe risk of head-of-line blocking when handling highly variable HTTP workloads (such as third-party webhooks).
- **When we would choose it**: We would have chosen Kafka if our throughput requirements were 100x higher (> 1,000,000 events/second), if we needed a persistent, long-term event log for multiple independent downstream consumers (such as analytics engines or data lakes), or if we had a dedicated Platform/SRE team to absorb the operational management overhead.

---

## Backlinks

- [ADR Index](index.md)
