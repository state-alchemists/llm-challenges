# ADR-001: Choosing Redis Streams for the Notification Subsystem

## Title
ADR-001: Selection of Redis Streams as the Messaging Backbone for the Decoupled Notification Subsystem

## Status
Accepted

## Context
Our SaaS project management platform is currently experiencing scaling and reliability issues with its notification module, which handles emails and webhooks synchronously within the HTTP request cycle of our Python/Flask monolith. With 85,000 monthly active users (MAU), ~2M monthly tasks created, and a peak traffic of ~500 requests per second (req/s), this synchronous processing has led to:
1. **Request Timeouts:** Blocking HTTP requests to send notifications leads to latency spikes (averaging 800ms and peaking at 8s during high traffic).
2. **Silent Failures:** Lack of retries or a Dead-Letter Queue (DLQ) means transient failures in third-party services (e.g., email providers or webhook endpoints) result in lost notifications.
3. **Cascading Failures:** External webhook latencies have exhausted database connection pools twice this year, taking down unrelated features.
4. **No Delivery Guarantees:** Billing-critical notifications (e.g., payment failures or trial expirations) have no delivery or deduplication guarantees.

### Scaling Target
- Decouple notifications from the HTTP request cycle to process them asynchronously.
- Support retry mechanisms with exponential backoff.
- Guarantee at-least-once delivery for billing events, and exactly-once semantics where feasible.
- Prepare the infrastructure to support real-time WebSocket push notifications within 2 quarters.
- Scale to handle a 10x increase in peak traffic (~5,000 req/s) without re-architecting.

### Constraints
- **Team Size & Expertise:** A small 6-person engineering team (3 senior, 3 mid-level) with **no dedicated infrastructure or DevOps engineer**.
- **Existing Footprint:** Redis is already deployed and maintained in production for session storage and rate limiting.
- **Experience:** No Kafka experience on the team today.
- **Timeline:** Must deliver business value within a strict 2-week window.
- **Budget:** Modest; managed enterprise solutions like Confluent Cloud are budget-prohibitive at our scale.

---

## Decision
We choose **Redis Streams** as the messaging backbone for our notification subsystem. 

### Justification

#### 1. Low Operational Complexity and Existing Infrastructure
The most significant constraint is our team size (6 engineers) and the absence of a dedicated infrastructure engineer. We already run and maintain Redis in production for sessions and rate limiting. Adopting Redis Streams requires **zero additional infrastructure provisioning, licensing, or maintenance overhead**. 
In contrast, deploying and managing Apache Kafka in-house requires deep expertise in JVM tuning, disk I/O management, cluster replication, and KRaft/ZooKeeper coordination. Given our budget and team size, the operational overhead of Kafka represents a critical risk of failure.

#### 2. Meeting the 2-Week Setup/Migration Target
Since the team already understands Redis, the learning curve is minimal. Using Python's standard `redis-py` library, we can implement Redis Streams producer and consumer logic within days. This ensures we easily meet the 2-week deadline to decouple notifications, whereas setting up a production-grade, highly available Kafka cluster from scratch would take weeks of learning, testing, and deployment.

#### 3. Throughput and Scalability
Our current peak is ~500 req/s, and our 10x target is ~5,000 req/s. 
- **Redis Streams** operates in-memory and is capable of processing over 100,000 operations per second on a single, modest virtual machine. It easily handles our 10x scaling target of 5,000 req/s with substantial headroom.
- **Apache Kafka** is designed for extreme throughput (millions of events per second), which is vastly overkill for our notification subsystem.

#### 4. Strong Ordering Guarantees
Redis Streams ensures strict FIFO (First-In-First-Out) ordering of messages within a stream. Each message is appended with a monotonically increasing ID (e.g., `<timestamp>-<sequence>`), which is perfect for maintaining the sequence of task updates and assignments.

#### 5. Consumer Groups and Work Distribution
Redis Streams natively supports consumer groups (`XGROUP`, `XREADGROUP`). This allows us to scale out multiple concurrent consumer workers (running as independent Python processes) to process notifications in parallel. Redis Streams tracks which consumer is processing which message using a Pending Entries List (PEL). If a consumer crashes, other consumers can inspect the PEL and claim stalled messages using `XCLAIM`, ensuring robust fault tolerance.

#### 6. Achieving Exactly-Once Semantics (EOS)
Billing notifications must be delivered reliably.
- **The Physical Impossibility of End-to-End Exactly-Once:** Sending notifications inherently involves communicating with external, non-transactional third-party APIs (e.g., SMTP servers, SendGrid, external webhook URLs). Due to the fundamental limit of distributed systems (the Two Generals' Problem), if a consumer successfully sends an email but crashes before acknowledging the message broker, a retry is inevitable. Physical end-to-end exactly-once delivery across external networks is impossible.
- **The Application-Level Solution:** We will implement **exactly-once semantics** at the application layer through **at-least-once delivery combined with idempotent consumer processing**:
  1. **At-Least-Once Delivery:** Handled by Redis Streams' consumer group acknowledgements (`XACK`). Consumers only acknowledge a message after successfully completing the notification delivery.
  2. **Idempotency on the Consumer Side:** We will generate a unique `event_id` or utilize the auto-generated Redis Stream message ID (e.g., `1685432100000-0`). Before a consumer executes a notification (such as charging a user or sending a billing email), it will attempt to write this ID into a PostgreSQL deduplication/idempotency table (or a Redis-based lock with an TTL) within a database transaction. If the ID already exists, the notification is discarded as a duplicate.

#### 7. Message Retention
Redis Streams retains messages in memory, but supports efficient truncation using the `MAXLEN` option (e.g., `XADD mystream MAXLEN ~ 10000 *`). This allows us to cap memory usage. Because notifications are transient delivery tasks rather than historical event-sourcing records, we do not need infinite retention inside the message broker. Once a notification is delivered and acknowledged, it can be safely discarded from Redis. Permanent audit logs and delivery history will be stored in our PostgreSQL read replica / primary database.

#### 8. Strategic Alignment with WebSocket Push
Redis provides a native Pub/Sub model. Choosing Redis Streams as our message broker aligns perfectly with our two-quarter target of adding real-time WebSocket push notifications, as we can easily bridge Redis Streams to Redis Pub/Sub channels to broadcast live updates to our WebSocket servers.

---

## Consequences

### Pros (Benefits)
- **Zero New Infrastructure:** No extra servers, cluster coordinators, or cloud bills. Leverage existing Redis deployment.
- **Rapid Time-to-Market:** Meets the 2-week implementation constraint easily.
- **Extremely Low Latency:** Sub-millisecond queue write latency avoids blocking the main Flask HTTP request thread.
- **Robust Work Distribution:** Native consumer groups allow horizontal scaling of notification workers.
- **Fault-Tolerant Retries:** Built-in message acknowledgement (`XACK`), pending tracking (`XPENDING`), and claiming (`XCLAIM`) prevent silent failures and support implementing exponential backoff with dead-letter streams.

### Cons (Trade-offs and Mitigations)
- **In-Memory Limits:** Redis is an in-memory data store. If Redis runs out of memory, it may evict keys or fail to append new messages.
  * *Mitigation:* We will enforce strict message size limits, apply stream truncation (`MAXLEN ~ 50000`), and run dedicated workers to process and clear queues rapidly. Furthermore, we can configure Redis persistence (`AOF` with `appendfsync everysec`) to ensure minimal data loss in the event of a crash.
- **No Long-Term Replayability:** Unlike Kafka, which persists logs indefinitely to disk, Redis is constrained by RAM and cannot act as a long-term analytical data lake.
  * *Mitigation:* We will offload persistent transaction logs, delivery audit logs, and status records directly to our PostgreSQL database, keeping the message broker lean and transient.
- **Scale Limit of Single Redis Instance:** Scaling past a single node's RAM/CPU requires moving to Redis Cluster or partitioning streams manually.
  * *Mitigation:* A single Redis node can handle >100,000 operations per second, which easily accommodates our 10x target (5,000 req/s). Horizontal scaling is a distant concern that does not justify the immediate operational penalty of Kafka.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
- **Excessive Operational Overhead:** Self-hosting a highly available Kafka cluster requires managing ZooKeeper/KRaft, brokers, JVMs, and garbage collection. With only 6 engineers and no dedicated infrastructure engineer, this is an unacceptable operational burden.
- **High Learning Curve:** The team has zero Kafka experience. Training, prototyping, and configuring Kafka correctly would take significantly longer than the 2-week constraint.
- **Prohibitive Cost:** Fully managed Kafka (e.g., Confluent Cloud) is too expensive for our modest budget.
- **Inappropriate Scale:** Kafka is designed for high-volume telemetry, stream-processing, and multi-terabyte data lakes. For a SaaS project management notification subsystem processing ~2M tasks/month, Kafka is a severe case of over-engineering.
