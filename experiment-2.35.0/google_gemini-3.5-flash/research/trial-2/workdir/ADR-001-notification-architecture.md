# ADR-001: Notification Subsystem Architecture Selection

- **Status**: Proposed
- **Date**: 2026-06-15
- **Deciders**: Zaruba (Lead Architect), SaaS Project Management Platform Engineering Team
- **Context tags**: architecture, notification, message-queue, scale

## Context

We operate a SaaS project management platform serving 85,000 monthly active users, processing approximately 2 million tasks created per month, and sustaining a peak load of ~500 requests/second (req/s) during business hours. 

### Current Architecture
* **Backend**: Python/Flask monolith (~50k lines of code).
* **Database**: PostgreSQL (single primary, one read replica).
* **Cache**: Redis (currently used for session storage and rate limiting).
* **Notification System**: Handled synchronously inside the HTTP request-response cycle.

### The Problem
Processing email and webhook notifications synchronously has introduced several critical failure modes:
1. **Request Timeouts**: Sending notifications blocks the response. Average latency is 800ms, spiking to 8s during peak traffic.
2. **Silent Failures**: If an downstream email provider or webhook endpoint is down, notifications are silently dropped with no retries or dead-letter queue (DLQ).
3. **Cascading Failures**: Unresponsive or slow external webhook endpoints have twice caused connection pool exhaustion, bringing down unrelated platform features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") have no transactional or delivery guarantees.

### Scaling Target
To handle a projected 10x traffic growth without re-architecting (moving from ~500 req/s to ~5,000 req/s), we must:
* Decouple notifications from the HTTP request cycle via asynchronous processing.
* Support robust retry policies with exponential backoff.
* Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
* Add real-time WebSocket push notifications within two quarters.

### Constraints
* **Team**: 6 engineers (3 senior, 3 mid-level) with no dedicated SRE or infrastructure engineer.
* **Timeline**: Must not require more than 2 weeks of setup and migration work before delivering value.
* **Budget**: Modest budget; cannot afford a fully managed enterprise event stream (e.g., Confluent Cloud Kafka) at our projected scale today.
* **Experience**: The team already operates and understands Redis in production, but has zero Apache Kafka experience.

---

## Decision

We will use **Redis Streams** as the backbone for our asynchronous notification subsystem. 

Given our tight 2-week implementation constraint, modest budget, and 6-person engineering team, introducing Apache Kafka would impose unacceptable operational complexity. Redis is already running in our production environment, meaning zero setup friction and minimal cognitive load for the team. Redis Streams provides the necessary queuing, consumer group partitioning, and delivery guarantees to meet our 10x scaling targets (~5,000 req/s) with extreme reliability.

---

## Technical Evaluation and Justification

### 1. Throughput and Performance
* **Requirement**: Handle 10x traffic growth up to a peak of 5,000 req/s.
* **Redis Streams**: Being in-memory, Redis can easily achieve 50,000 to 100,000 read/write operations per second on modest single-core hardware. A peak of 5,000 req/s represents less than 10% of Redis's single-threaded capability, leaving massive headroom.
* **Kafka**: Capable of millions of writes/sec across multi-broker clusters. However, this level of throughput is vastly superior to our current and medium-term requirements and represents unnecessary over-provisioning.

### 2. Operational Complexity
* **Requirement**: Delivery of value within 2 weeks by a 6-person team with no dedicated SRE.
* **Redis Streams**: Zero new infrastructure is required. We already monitor, scale, and back up Redis. We can implement producers and consumers using standard Python clients (such as `redis-py`) within days.
* **Kafka**: High operational overhead. Setting up a production-ready, highly available Kafka cluster (via KRaft or ZooKeeper) requires intensive JVM tuning, disk I/O optimization, partition count planning, and replication factor management. The team would spend the entire 2-week window on infrastructure staging rather than feature delivery.

### 3. Ordering Guarantees
* **Requirement**: Sequential delivery of notifications (e.g., "Task Created" must precede "Task Completed").
* **Redis Streams**: Guarantees strict FIFO ordering per stream. Because entries are appended to a single stream key, and Redis commands execute single-threaded, messages are naturally serialized.
* **Kafka**: Guarantees order only *within a partition*. Ensuring global ordering requires partition-key mapping, adding implementation overhead to the producers.

### 4. Consumer Groups
* **Requirement**: Scale consumer workers horizontally to handle peak load and enable retries.
* **Redis Streams**: Natively supports consumer groups (via `XGROUP` and `XREADGROUP`). This allows us to spin up multiple concurrent workers. It tracks unacknowledged messages per consumer using a Pending Entries List (PEL). If a worker crashes mid-processing, other workers can identify stale messages via `XPENDING` and claim ownership using `XCLAIM`, ensuring robust horizontal scaling and fault tolerance.
* **Kafka**: Natively supports consumer groups with automated partition rebalancing. While powerful, Kafka rebalances are notoriously heavy operations that can pause consumption, introducing latency spikes under load.

### 5. Message Retention and Durability
* **Requirement**: Decoupled, asynchronous processing without memory exhaustion.
* **Redis Streams**: Operates in-memory. Because memory is finite and expensive, we must cap our stream lengths using the `MAXLEN` modifier (e.g., `XADD notification_stream MAXLEN ~ 100000`). Since notifications are transient events (once processed and acknowledged, they do not need to persist in the message log), capping streams is an ideal memory-management strategy. For permanent audit logs, we will record successfully dispatched notifications to our existing PostgreSQL read replica.
* **Kafka**: Designed for long-term on-disk durability and message replaying. While durable, we do not require multi-day message replayability for simple notifications, making Kafka's disk management an unnecessary overhead.

### 6. Exactly-Once Semantics (EOS) for Billing
* **Requirement**: Billing notifications must not be processed multiple times.
* **The Reality**: In a distributed system, true end-to-end exactly-once delivery across external networks (e.g., SMTP servers, third-party webhook endpoints) is mathematically impossible due to network partitions (the "Two Generals' Problem"). Therefore, exactly-once processing must be achieved via **at-least-once delivery with idempotent consumer deduplication**.
* **Redis Streams Implementation**: 
  1. Redis Streams generates unique, monotonic IDs (e.g., `1518912345000-0`) for every message.
  2. Workers process billing notifications inside a PostgreSQL database transaction.
  3. The transaction attempts to insert the Redis message ID into an idempotent log table:
     ```sql
     INSERT INTO processed_notifications (message_id, processed_at)
     VALUES (:message_id, NOW())
     ON CONFLICT (message_id) DO NOTHING;
     ```
  4. If a duplicate message is delivered (due to a previous network acknowledgement failure), the unique constraint on `message_id` triggers a conflict, rolling back the transaction and bypassing redundant notification dispatch. This guarantees exactly-once processing without any of the heavy distributed transaction log configurations required by Kafka.

---

## Consequences

### Positive (Pros)
* **Immediate Time-to-Value**: Implementation, testing, and deployment can be completed within 1 week, well under our 2-week limit.
* **Operational Simplicity**: Leverages our existing Redis stack, incurring $0 in additional infrastructure costs and requiring 0 hours of cluster setup.
* **Ultra-low Latency**: In-memory message publication and consumption occur with sub-millisecond overhead.
* **WebSocket-Ready**: Redis has native Pub/Sub and Streams mechanisms that seamlessly align with our 2-quarter target for real-time WebSocket pushes.

### Negative (Cons)
* **Memory Limits**: Storing large backlogs of unacknowledged notifications in Redis could exhaust system RAM. We must enforce strict stream capping (`MAXLEN`) and configure Prometheus alerts on memory consumption and PEL length.
* **Failover Data Loss Risk**: If a Redis primary node crashes before replication syncs to the replica (and before `fsync` completes on AOF), a small window of messages could be lost. We mitigate this by:
  1. Setting `appendfsync everysec` in Redis configuration.
  2. Saving critical billing events in our highly durable PostgreSQL primary (Transactional Outbox Pattern) before pushing to Redis Streams, assuring PostgreSQL remains the ultimate source of truth.

### Follow-ups
1. **Outbox Implementation**: Write a lightweight decorator to log billing events to a PostgreSQL `outbox` table during the primary database transaction.
2. **Monitoring Setup**: Configure AWS CloudWatch and Prometheus alerts to monitor Redis memory usage and `XPENDING` count.
3. **Dead-Letter Queue (DLQ)**: Implement a mechanism where a message with `delivery_attempts > 5` is moved to a `notification_dlq` stream for manual auditing.

---

## Alternatives Considered

### Apache Kafka
* **Why Rejected**: Implementing Kafka was rejected due to its immense operational complexity and high cost. With only 6 engineers and no dedicated infrastructure engineer, managing KRaft/ZooKeeper, disk provisioning, JVM tuning, and broker failovers would severely distract the team from product delivery. Furthermore, managed services like Confluent Cloud violate our modest budget constraints. 
* **When we would have chosen Kafka**: We would have chosen Apache Kafka if our throughput exceeded 100,000 messages/second, if we required permanent, multi-day message retention on-disk, or if our architecture was heavily reliant on event sourcing and stream processing engines (e.g., Kafka Streams, Apache Flink).

---

## Backlinks

* [System Context](system_context.md)
