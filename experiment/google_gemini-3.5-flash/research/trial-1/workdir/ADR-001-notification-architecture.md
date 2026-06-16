# Title: ADR-001 - Notification Subsystem Architecture Decision

- **Status**: Proposed
- **Date**: 2026-06-16
- **Deciders**: Engineering Team (3 senior, 3 mid-level engineers)
- **Context tags**: messaging, notifications, redis-streams, architecture

---

## Context

Our SaaS project management platform currently services 85,000 monthly active users (MAU), generating ~2 million tasks per month, with a peak load of ~500 requests per second (req/s) during business hours. 

The notifications module—responsible for dispatching emails and webhooks when tasks are updated, assigned, or completed—is currently coupled synchronously to the HTTP request cycle of our Python/Flask monolith. This design has introduced severe production issues:
1. **Request Timeouts**: Sending notifications blocks HTTP responses, driving average request latency to 800ms, with peak spikes reaching 8 seconds.
2. **Silent Failures**: Transient downstream outages (e.g., email providers or webhook endpoints) result in lost notifications because there is no retry mechanism or Dead Letter Queue (DLQ).
3. **Cascading Failures**: Slow downstream webhook targets have twice exhausted our PostgreSQL connection pool this year, taking down unrelated platform features.
4. **Lack of Delivery Guarantees**: Critical billing-related events (e.g., "payment failed", "trial expired") are processed without transactional guarantees or exactly-once semantics.

To resolve these vulnerabilities and handle a projected 10x traffic growth (reaching ~5,000 req/s peak and ~20 million tasks/month), we must transition to an asynchronous, decoupled notification architecture. 

### Constraints
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure/platform engineer.
- **Operational Overhead**: The team has zero Kafka experience, but already operates Redis in production for session storage and rate limiting.
- **Timeframe**: Setup and migration must deliver initial value within a strict 2-week window.
- **Budget**: Modest. The company cannot afford the significant licensing and infrastructure costs of managed event-streaming platforms like Confluent Cloud.
- **Delivery Requirements**: Billing notifications must guarantee exactly-once semantics (EOS), while other notifications require at-least-once delivery with exponential backoff and retry capabilities. Real-time WebSocket pushes must be supported within 2 quarters.

---

## Decision

We will use **Redis Streams** as our message broker for the notification subsystem. We will use the existing production Redis instance (or a dedicated Redis cluster node) to run Redis Streams. 

To achieve exactly-once delivery for billing-critical events, we will implement a hybrid approach: **at-least-once delivery guaranteed by Redis Streams consumer groups, paired with consumer-side idempotency verified within our PostgreSQL primary database.**

### Technical Justification

#### 1. Throughput & Scalability
Our current peak is ~500 req/s, and our 10x scaling target requires supporting ~5,000 req/s. 
- **Redis Streams**: Being fully in-memory, a single Redis instance can easily process 50,000+ write/read operations per second. Redis Streams can effortlessly handle our 10x target with single-digit millisecond latency and negligible CPU overhead.
- **Apache Kafka**: Designed for millions of events per second, which is a massive over-provisioning of capabilities for our scale. Introducing Kafka's partition-based distributed architecture for a 5,000 req/s workload introduces unnecessary complexity with no performance benefit.

#### 2. Ordering Guarantees
Our notification system must preserve the strict chronological sequence of tasks (e.g., *Task Created* must be processed before *Task Assigned*, which must precede *Task Completed*).
- **Redis Streams**: Guarantees strict chronological ordering per stream by utilizing an auto-generated, time-based unique ID (`<millisecondsTime>-<sequenceNumber>`) for every appended message. 
- **Apache Kafka**: Guarantees ordering only within a single partition. To maintain task ordering, we would have to implement message keying (e.g., partitioning on `task_id`). Redis Streams provides this chronological guarantee out-of-the-box without requiring complex partition key designs.

#### 3. Message Retention & Memory Bounding
- **Redis Streams**: Since Redis is an in-memory database, infinite message retention is a liability. However, notifications are transient events; once processed, sent, and acknowledged, there is no requirement to persist them in-memory. We will enforce memory bounding using capped streams via the `XADD` command with `MAXLEN ~ N` or `MINID` (e.g., retaining only the last 100,000 messages). PostgreSQL remains our durable system of record; Redis Streams is used solely as an operational buffer.
- **Apache Kafka**: Kafka persists all messages to disk, allowing long-term retention and historical playbacks. While powerful, disk-backed persistence requires active storage management, disk volume scaling, and compaction strategies. Because our PostgreSQL database already stores the historical state of tasks and users, we do not need a secondary, disk-backed historical event store.

#### 4. Consumer Groups & Worker Scalability
Both technologies support the consumer group model to distribute message processing across parallel worker processes.
- **Redis Streams**: Natively supports consumer groups (via `XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, and `XCLAIM`). Consumer groups allow us to scale out Flask background worker processes (e.g., running via Celery or Python-RQ) to consume notifications in parallel. Redis tracks pending/unacknowledged messages per consumer. If a worker dies mid-processing, other workers can claim those abandoned messages using `XCLAIM`.
- **Apache Kafka**: Kafka consumer groups manage offsets client-side or in internal brokers. However, Kafka's consumer coordination mechanism is highly sensitive. Slow workers (e.g., workers blocked by slow downstream webhooks or email APIs) can cause consumers to miss heartbeats, triggering "rebalance storms." During a rebalance storm, message consumption freezes across all workers, which would exacerbate our existing latency issues. Redis Streams' `XPENDING` tracking is non-blocking and completely avoids rebalance freezes.

#### 5. Exactly-Once Semantics (EOS) Strategy
- **Apache Kafka**: Natively supports EOS using transactional producers, consumer offset commits, and two-phase commits. However, configuring and maintaining Kafka transactions in a Python environment is extremely complex and poorly supported by Python clients. It also adds substantial latency and coordination overhead.
- **Redis Streams**: Provides at-least-once delivery (a message is re-delivered if a consumer crashes before calling `XACK`). To achieve exactly-once delivery for billing-critical events, we will rely on a standard **idempotent consumer pattern** utilizing our PostgreSQL database. 
  When a consumer pulls a billing event, it processes the notification and logs the event's unique Redis ID (or a UUID generated at the publisher) inside a PostgreSQL `processed_notifications` table within a single ACID transaction. If the transaction succeeds, the notification is sent and `XACK` is called. If the consumer crashes and the message is redelivered, the database's unique constraint on `notification_id` will abort the transaction, preventing duplicate processing. Since Postgres is already our primary database, this implementation requires no new infrastructure, leverages existing transaction code, and is 100% reliable.

#### 6. Operational Complexity & Constraints
- **Redis Streams**: Zero operational overhead. We already run Redis in production. No new infrastructure, vendors, monitoring tools, or firewall rules are needed. The 6-person team is already comfortable monitoring Redis memory and performance. Setup and migration will take less than 3 days, easily fitting within the 2-week constraint.
- **Apache Kafka**: Operating Kafka is a massive infrastructure undertaking, requiring a Kafka cluster (brokers, ZooKeeper/KRaft) and specialized knowledge in cluster sizing, replication factors, and JVM tuning. Without a dedicated infrastructure engineer, self-hosting is a severe operational risk. Managed Kafka services (e.g., Confluent Cloud) would violate our modest budget constraint. The steep learning curve and setup time would easily blow past the 2-week limit.

---

## Consequences

### Positive (Pros)
- **Zero Infrastructure Setup**: Eliminates the need to provision, secure, or pay for new messaging clusters. We leverage our existing Redis deployment.
- **Rapid Time-to-Value**: The 6-person engineering team can implement, test, and deploy Redis Streams-based workers within the 2-week timeline.
- **Minimal Cognitive Overhead**: The team does not need to learn Kafka-specific concepts (e.g., partitions, replication, ZooKeeper, brokers, rebalancing).
- **Extremely Low Latency**: In-memory message delivery guarantees sub-millisecond dispatch times, instantly decoupling our web servers and solving request timeouts.
- **Ready for WebSockets**: Real-time push notifications can be integrated natively using Redis Pub/Sub alongside Redis Streams, laying a clean foundation for the Q3/Q4 WebSocket requirements.
- **Robust Failure Isolation**: Isolates slow email and webhook workers from the web servers, preventing downstream outages from causing PostgreSQL connection pool exhaustion.

### Negative (Cons)
- **In-Memory Bounding Required**: Because Redis is in-memory, we must carefully configure stream capping (`MAXLEN`) and monitor Redis memory usage to prevent Out-Of-Memory (OOM) errors if consumers fall behind.
- **No Long-Term Message Playback**: Unlike Kafka, which allows replaying weeks of historical messages from disk, Redis Streams must remain capped. If a bug is found in notification logic, we cannot replay weeks of old events from the broker. (However, we can reconstruct history from PostgreSQL audit logs if absolutely necessary).
- **Requires Custom Idempotency Logic**: We must manually implement and maintain the PostgreSQL-based unique constraint checks for billing-critical exactly-once semantics.

### Follow-ups
1. **Memory Monitoring**: Set up AWS CloudWatch alerts on Redis memory utilization and configure maxmemory policies.
2. **Stream Capping Policies**: Standardize on `XADD stream_name MAXLEN ~ 50000` to prevent unbounded memory growth.
3. **Dead Letter Queue (DLQ)**: Implement a worker-side mechanism to inspect `XPENDING` retry counts. If a message fails delivery more than 5 times, move it to a dedicated `notifications:dlq` stream for manual inspection or alert routing.
4. **Postgres Idempotency Table**: Create the `processed_notifications` schema with a unique index on `(event_id, consumer_group)` to lock down the exactly-once billing logic.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka due to its high operational complexity, steep learning curve, and budget requirements. 

**Why it was rejected**:
- Setting up and operating Kafka without a dedicated infrastructure engineer introduces unacceptable reliability risks to the platform.
- The 6-person team would need to invest weeks of learning and testing to safely implement and monitor Kafka clients in Python. This violates the 2-week delivery constraint.
- Managed Kafka solutions (like Confluent Cloud) are cost-prohibitive for our modest budget.
- Kafka’s advanced capabilities, such as stream processing (KSQL/Kafka Streams) and infinite disk-backed retention, are unnecessary since our data is transient and our primary monolith uses PostgreSQL for long-term state.

**What would have made Kafka the winner**:
We would have chosen Apache Kafka if our peak throughput exceeded 50,000 req/s, if we required real-time stream processing/analytics on event pipelines, if we lacked PostgreSQL as a persistent transaction store, or if we had a dedicated platform engineering team to manage the cluster infrastructure.

---

## Backlinks
- [ADR Index](index.md)
