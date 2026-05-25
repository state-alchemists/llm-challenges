# ADR-001: Architecture Decision for the SaaS Notification Subsystem

- **Status**: Proposed
- **Date**: 2026-05-25
- **Deciders**: Engineering Team
- **Context Tags**: messaging, notifications, redis-streams, kafka, architecture

## Context

### Problem Statement
Our SaaS project management platform (85,000 monthly active users, ~2M tasks created/month, peak ~500 req/s) currently handles task notifications (emails and webhooks) synchronously within the HTTP request cycle of our Python/Flask monolith. This blocking approach has introduced critical issues as we scale:
1. **Request Timeouts**: Sending notifications blocks HTTP responses, increasing average latency to 800ms with peaks up to 8s.
2. **Silent Failures**: Downed downstream providers (email or webhook endpoints) result in silently dropped notifications due to a lack of retries or a Dead-Letter Queue (DLQ).
3. **Cascading Failures**: Unstable external webhook endpoints have caused database connection pool exhaustion twice this year, taking down unrelated monolith features.
4. **No Delivery Guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") require absolute delivery guarantees, but none exist today.

### Scaling Targets
- Decouple notifications from the synchronous HTTP request cycle using asynchronous background processing.
- Implement robust retry mechanisms with exponential backoff.
- Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- Support real-time WebSocket push notifications within 2 quarters.
- Scale to handle a 10x traffic growth (reaching peak ~5,000 req/s) without requiring a complete re-architecture.

### Core Constraints
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure/DevOps engineer.
- **Technology Footprint**: We already run Redis in production for session storage and rate limiting.
- **Experience**: The team has zero experience operating or developing with Apache Kafka today.
- **Time to Market**: The new system must be fully set up, migrated, and delivering value within 2 weeks.
- **Budget**: Modest budget; managed Kafka solutions like Confluent Cloud are financially non-viable at full scale today.
- **Exactly-Once Semantics (EOS)**: Strictly required for billing-critical events.

---

## Decision

We will use **Redis Streams** to power the asynchronous notification subsystem.

### Justification Summary
Redis Streams meets all functional and non-functional requirements at our target 10x scale with near-zero operational overhead. It enables us to utilize our existing production Redis infrastructure, entirely avoiding the operational risks, budget constraints, and long learning curve of Apache Kafka. This ensures we can easily meet our strict 2-week delivery timeline with our 6-person team.

---

## Technical Comparison Matrix

| Property | Redis Streams | Apache Kafka |
| :--- | :--- | :--- |
| **Operational Complexity** | Extremely Low (already running in prod, standard key-value paradigm). | Extremely High (requires ZooKeeper/KRaft, multi-broker cluster, complex JVM tuning). |
| **Setup & Migration Time** | Hours to days (fully achievable within the 2-week constraint). | Several weeks to months (impossible to deliver value within 2 weeks). |
| **Throughput & Latency** | Sub-millisecond latency; >50,000 ops/s on modest hardware. Fully scales to the 10x target of 5,000 req/s. | Millions of ops/s; highly distributed, but high latency overhead relative to Redis. |
| **Ordering Guarantees** | Strict total order per stream key using chronological ID generation (`<ms>-<seq>`). | Strict order within a partition; requires managing partition keys. |
| **Message Retention** | In-memory with RDB/AOF persistence; requires stream trimming (`MAXLEN` / `MINID`). | Durable, multi-disk log storage; support for infinite/long retention. |
| **Consumer Groups** | Native via `XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM` for work distribution. | Native with partition rebalancing; highly scalable but complex partition assignment. |
| **Exactly-Once Semantics** | Achieved via application-level consumer deduplication. | Supported via transactions, but still requires application deduplication for external APIs. |
| **Operational Cost** | Minimal incremental cost (reuses existing Redis instances or minimal vertical scale-up). | Extremely expensive (requires Confluent Cloud or dedicated self-managed EC2 clusters). |

---

## Rationale: Why Redis Streams Won

### 1. Zero New Operational Complexity & Rapid Delivery (2-Week Constraint)
Operating a multi-broker Apache Kafka cluster requires a dedicated infrastructure engineer to configure JVM memory, manage KRaft/ZooKeeper metadata, handle broker failures, and tune disk OS parameters. Without existing Kafka expertise, our 6-person team would spend the entire 2-week timeline fighting Kafka infrastructure and client library configurations.
In contrast, Redis is already running and monitored in our production stack. Our team is fully comfortable with its programming model. Designing, developing, and deploying a Redis Streams-based solution can be comfortably completed within a single week, leaving a week for testing, verification, and migration.

### 2. Throughput at 10x Scale
At our current peak of 500 req/s, the notification load is trivial. Even at our 10x scaling target (~5,000 req/s), Redis Streams can easily handle the load. A single, moderately sized Redis node can handle over 50,000 read/write operations per second. Since notifications are transient events that are consumed and processed quickly, they do not require a massive distributed system like Kafka.

### 3. Native Consumer Groups & Reliability Guarantees
Redis Streams features native consumer groups via `XGROUP` and `XREADGROUP`. This allows us to scale out multiple stateless Python worker processes (e.g., using Celery or a custom Python loop) to consume notifications concurrently:
- **At-Least-Once Delivery**: Redis tracks pending (unacknowledged) messages per consumer in a Pending Entries List (PEL) via `XPENDING`. If a worker dies mid-execution, another worker can inspect the PEL, claim the dead message using `XCLAIM`, retry it, and acknowledge it using `XACK`.
- **Stream Trimming**: To prevent memory exhaustion, we will use approximate trimming (`XADD mystream MAXLEN ~ 10000`) or trim by age during publishing. Since permanent notification logs and audit trails are persisted in our primary PostgreSQL database upon successful delivery, Redis Streams only needs to hold active queue backlogs, keeping memory utilization bounded and predictable.

### 4. Exactly-Once Semantics for Billing Notifications
No message broker can provide native "out-of-the-box" exactly-once delivery to external third-party systems like Stripe, Twilio, or SendGrid. Network partitions can always prevent an acknowledgment from reaching the broker after a message is successfully delivered to the recipient, leading to a duplicate delivery during retries.
To achieve exactly-once semantics for critical billing notifications, we must implement an **idempotent consumer pattern** at the application level:
- When a billing event occurs, a unique idempotency token is generated.
- Inside a PostgreSQL database transaction, the worker checks if the token has already been processed in an `idempotent_consumers` table.
- If it has, the worker silently acknowledges the message and returns. If not, the worker executes the billing notification action, writes the token to PostgreSQL, and commits the transaction.
Because this deduplication layer is mandatory under both architectures, Kafka's native transactional APIs provide no added benefit for external integrations, while Redis's high-speed key-value storage offers an alternative, super-fast rate-limiting and locking layer for deduplication.

### 5. Seamless WebSocket & Real-time Support
To deliver real-time WebSocket push notifications within 2 quarters, our background workers can publish events to Redis Pub/Sub or dedicated Redis Streams. Our WebSocket servers (e.g., Python/gevent or Node.js) can easily subscribe to these Redis channels and push events to active browser connections. Redis is the industry standard for lightweight, real-time message broadcasting, whereas integrating WebSockets with Kafka requires complex bridging layers.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
- **Extreme Operational Overhead**: Managing ZooKeeper/KRaft, multi-node clusters, JVM parameters, and partition balancing is a full-time role. A 6-person team cannot afford to spend significant engineering hours on infrastructure maintenance.
- **Inability to Meet the Timeline**: Introducing Kafka requires building a deployment pipeline, writing custom Python wrappers (such as `confluent-kafka`), and testing cluster split-brain scenarios—tasks that cannot be resolved in 2 weeks.
- **Budgetary Constraints**: Running Kafka reliably in AWS requires at least 3 brokers for high availability. Given our modest budget, we cannot justify the high base cost of AWS MSK or Confluent Cloud at this stage of our growth.
- **Overkill for Scale**: Kafka is built to process gigabytes of log telemetry and millions of events per second. Scaling to 5,000 req/s does not justify adopting a highly complex, distributed streaming platform.

*We would have chosen Apache Kafka if:* Our peak throughput requirements exceeded 100,000 events per second, if we had a dedicated DevOps team, or if we required a multi-gigabyte persistent event-sourcing log with multi-week replayability.

---

## Consequences

### Positive (Pros)
- **Rapid Time-to-Value**: We can build, test, and ship the new system within our 2-week window.
- **Zero New Infrastructure**: Reuses our existing AWS ElastiCache / Redis setups, preserving our infrastructure budget.
- **Stateless Consumer Scaling**: Standard Python background workers can be scaled horizontally behind Redis consumer groups.
- **Low Memory Footprint**: Bounded stream lengths prevent memory leaks or exhaustion.
- **Built-in Real-time Core**: Pub/Sub and Streams provide all the building blocks needed for the upcoming WebSocket push notifications.

### Negative (Cons)
- **Memory Boundedness**: Redis is in-memory. Unlike Kafka, we cannot store months of notification history in Redis Streams without risking Out-Of-Memory (OOM) failures. We must strictly manage stream lengths and offload archival logs to PostgreSQL or AWS S3.
- **Broker Failures**: If the Redis primary instance fails, un-replicated stream messages in-flight could be lost (depending on standard AOF fsync configuration). We must configure Redis replication (multi-AZ replication groups) to mitigate this.
- **Manual Retries**: Implementing complex delay queues (e.g., retrying a message in 5 minutes, then 15 minutes, then 1 hour) in Redis Streams requires secondary structures (like Sorted Sets `ZSET` or secondary retry streams), whereas Kafka supports highly sophisticated retry-topic topologies.

### Follow-up Action Items
1. **Configure Redis Persistence & Replication**: Verify that our production AWS Redis setup has multi-AZ replication enabled and that AOF (Append-Only File) is configured with `everysec` to minimize data loss risk.
2. **Implement Stream Trimming**: Set up a strict limit on all notification stream writes using the `MAXLEN ~` argument to maintain memory usage safety.
3. **Design PostgreSQL Deduplication Table**: Create the database schema for idempotent consumer tracking of billing events to guarantee exactly-once processing.
4. **Develop Dead-Letter Queue (DLQ) Strategy**: Create a secondary stream (e.g., `notifications:dlq`) where messages that fail more than 5 times are moved for manual operator inspection.
5. **Establish Monitoring & Alerts**: Configure CloudWatch alerts on Redis memory usage (`DatabaseMemoryUsagePercentage`) and client connections to ensure early warning of queue backlog spikes.

---

## Backlinks
- [System Context: Notifier Subsystem](system_context.md)
