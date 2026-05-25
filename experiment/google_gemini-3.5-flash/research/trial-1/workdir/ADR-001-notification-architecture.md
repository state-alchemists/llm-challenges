# ADR-001 — Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-05-25
- **Deciders**: Engineering Team
- **Context tags**: notifications, async-processing, redis, kafka, messaging

## Context

We run a SaaS project management platform with 85,000 monthly active users (MAU), ~2 million tasks created per month, and a peak traffic of ~500 req/s during business hours. 

### Current Architecture
* **Backend**: Python/Flask monolith (~50k LOC)
* **Database**: PostgreSQL (single primary, one read replica)
* **Infrastructure**: 4 web servers behind an Nginx load balancer, hosted on AWS
* **Cache**: Redis (used for session storage and rate limiting today)
* **Notifications**: Handled synchronously inside the HTTP request cycle

### The Problems
As user activity has grown, synchronous notification dispatching (sending emails and webhooks) has caused significant stability and latency issues:
1. **Request Timeouts**: Sending notifications blocks HTTP web workers. Average response latency is 800ms, spiking to 8 seconds during peak hours.
2. **Silent Failures**: If third-party email providers or user-defined webhook endpoints are down, notifications are silently dropped. There are no retry mechanisms, backoffs, or Dead-Letter Queues (DLQs).
3. **Cascading Failures**: Unhandled slow webhook targets have caused PostgreSQL connection pool exhaustion twice this year, resulting in total downtime for unrelated features.
4. **No Delivery Guarantees**: Billing-critical events (e.g., "trial expired", "payment failed") are treated the same as transient notifications and offer no delivery guarantees.

### Constraints & Scaling Targets
* **Throughput Scaling**: The architecture must support 10x traffic growth (scaling to ~5,000 req/s and ~20 million tasks/month) without requiring a complete re-architecting phase.
* **Timeline**: The solution must require no more than 2 weeks of setup and migration work before delivering value.
* **Team**: A team of 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure/DevOps engineer** and **no prior experience with Apache Kafka**.
* **Budget**: Modest. We cannot afford managed Confluent Cloud or expensive managed enterprise messaging platforms at full scale.
* **Delivery Guarantees**: Must maintain exactly-once semantics for billing notifications, and guarantee at-least-once delivery with exponential backoff and DLQs for other notifications.
* **Real-time Push**: Must support real-time WebSocket push notifications within 2 quarters.

---

## Decision

> **We will use Redis Streams as the core messaging engine for the asynchronous notification subsystem.**

To satisfy the strict exactly-once semantics required for billing notifications, we will implement **at-least-once delivery** on the message stream combined with **application-level deduplication (idempotency)** using our existing, ACID-compliant PostgreSQL database.

---

## Rationale

Our decision is driven by evaluating specific technical properties of Redis Streams and Apache Kafka against our strict constraints:

### 1. Operational Complexity & Team Constraints
With a 6-person engineering team and no dedicated DevOps engineer, operational simplicity is the highest priority:
* **Redis Streams**: **Extremely low operational overhead.** We already run, monitor, and back up Redis in production for session storage and rate limiting. Deploying Redis Streams requires zero new infrastructure provisioning, zero licensing costs, and minimal learning curve.
* **Apache Kafka**: **Extremely high operational overhead.** Kafka is a distributed log engine requiring ZooKeeper or KRaft metadata management. Even managed offerings (such as AWS MSK) require fine-tuning of replication factors, partition counts, log retention policies, and consumer group rebalancing. A 6-person team with no Kafka experience would easily spend several weeks just configuring, testing, and securing Kafka, violating our 2-week setup constraint.

### 2. Exactly-Once Semantics (EOS) and External Systems
Our billing-critical notifications require exactly-once guarantees.
* **The Reality of External APIs**: True exactly-once delivery to external webhooks and email providers is physically impossible from a broker level alone. This is a consequence of the Two Generals' Problem: if a network partition occurs after an external email provider successfully processes a request but before returning an HTTP response, the notification worker must retry, leading to duplication.
* **The Solution**: Exactly-once processing *must* be solved at the application level.
* **Implementation Details**: We will generate a unique UUID for each notification event. Before sending an email or webhook, the background worker will attempt to insert this UUID into a PostgreSQL `processed_notifications` table inside an ACID transaction. A unique database constraint on the UUID will prevent duplicate processing. 
* **Evaluation**: Since application-level deduplication is mandatory under both systems to survive external network retries, Kafka's native, broker-internal Exactly-Once Semantics (EOS) provide no actual benefit for this use case. Redis Streams' reliable consumer group acknowledgement model is fully sufficient.

### 3. Throughput and Latency
* **Throughput**: Our 10x growth target is ~5,000 req/s. 
  * **Redis Streams** operates in-memory (with optional asynchronous AOF/RDB persistence to disk) and can easily handle over 50,000 write/read operations per second on a single modest instance.
  * **Apache Kafka** is optimized for extreme throughput (hundreds of thousands or millions of events/sec) using disk-backed batching, which is vastly over-engineered for our scale.
* **Latency**: Redis Streams provides sub-millisecond end-to-end latency, which is critical for real-time WebSocket push notifications. Kafka's latency is typically higher (single-to-double digit milliseconds) due to disk flushes and leader replication.

### 4. Message Retention and Storage
* **Redis Streams**: Uses memory to store messages. While memory is expensive, notification payloads are small and highly transient. Once a notification is sent or moved to a DLQ, its entry in the stream is no longer required. We can cap our streams using the `MAXLEN ~ 10000` parameter to prevent unbounded memory growth.
* **Apache Kafka**: Retains messages on disk indefinitely or based on time/size configuration. This is ideal for replayable event sourcing or data lakes, but unnecessary for a notification subsystem where transient queues and immediate delivery are the focus.

### 5. Consumer Groups & Concurrency
* **Redis Streams**: Supports robust consumer groups (`XGROUP`). Multiple workers can concurrently fetch and process messages. Redis tracks unacknowledged messages per consumer using a Pending Entries List (PEL). If a worker crashes, other workers can identify and claim stale messages using `XPENDING` and `XCLAIM`, ensuring reliable at-least-once delivery.
* **Apache Kafka**: Offers excellent consumer group features but scales concurrency strictly by partitioning topics. If a topic has 4 partitions, you cannot have more than 4 concurrent active consumers in a group. Redis Streams allows us to scale consumers up and down dynamically without worrying about partition constraints.

### 6. Ordering Guarantees
* **Redis Streams**: Guarantees strict chronological ordering (FIFO) within a single stream based on its auto-generated message IDs (e.g., `<timestamp>-<sequence_number>`).
* **Apache Kafka**: Guarantees ordering only within a single partition.
* Since our notifications are bound to specific tasks or users, we can easily maintain sequential ordering by routing user-specific notification requests through user-sharded queues or simply processing them in a single stream where local user events naturally flow sequentially.

---

## Consequences

Choosing Redis Streams commits us to specific operational patterns and introduces trade-offs we must actively manage:

### Positive Consequences (Pros)
* **Rapid Delivery**: The team can deploy the asynchronous notification engine to production in under a week, leaving time to build retries, backoffs, and DLQs within the 2-week budget.
* **Minimal Budget Impact**: Reusing our existing Redis deployment results in $0 of incremental infrastructure costs.
* **Low Training Cost**: The entire team of 6 can instantly understand and debug Redis Streams using standard commands (`XADD`, `XREADGROUP`, `XACK`).
* **System Stability**: Offloading notification work to background workers completely protects our HTTP request cycles and PostgreSQL connection pools from slow or failing external APIs.

### Negative Consequences (Cons)
* **Memory Limits**: Because Redis stores streams in-memory, we must enforce strict stream length caps (`MAXLEN`) on all notification channels. If we fail to cap a high-volume stream, Redis could run Out-Of-Memory (OOM) and crash, impacting sessions and rate-limiting.
* **Durability Trade-offs**: Redis persistence (AOF/RDB) is typically configured asynchronously to maintain high performance. In a catastrophic event (such as a primary Redis instance crashing exactly when the replica fails, prior to disk sync), a tiny window of notification messages (usually <1 second) could be lost. We mitigate this by persisting critical events (like billing actions) in PostgreSQL first before publishing them to the Redis Stream.
* **Custom Backoff Logic**: While Redis Streams tracks pending messages, we must write custom Python logic in our workers to handle exponential backoff and routing to a Dead-Letter Stream (DLQ) when retries are exhausted.

### Follow-Ups and Action Items
1. **Define Stream Topology**: Implement a standard naming convention: `stream:notifications:general` for standard events and `stream:notifications:billing` for critical events.
2. **Configure Memory Safety**: Enforce `MAXLEN ~ 10000` on all `XADD` operations.
3. **Build the Idempotency Layer**: Implement the PostgreSQL-backed `processed_notifications` table and decorate billing-consumer functions with a Python idempotency decorator.
4. **Setup Alerts**: Configure Datadog/CloudWatch alerts on Redis memory usage and the size of the Pending Entries List (PEL) to detect stuck workers.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for this architecture. While Kafka is a industry standard for high-throughput stream processing, it is a poor fit for our constraints:
* **Why it was rejected**: It introduces extreme operational complexity and requires a dedicated infrastructure team to manage securely. Our modest budget cannot support managed Confluent Cloud at scale, and self-hosting Kafka would violate our 2-week timeline.
* **What would make Kafka win**: We would only choose Kafka if our platform grew to handle >100,000 req/s, if we had a dedicated DevOps team, or if we needed to perform complex stream analysis, event-sourcing, or log replayability over weeks or months of historical data.

---

## Backlinks
* [README.md](README.md)
