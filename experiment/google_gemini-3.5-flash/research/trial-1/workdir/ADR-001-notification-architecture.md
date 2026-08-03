# ADR-001: Notification Subsystem Architecture

## Status

**Status**: Proposed  
**Date**: 2026-08-03  
**Deciders**: Engineering Team (3 Senior, 3 Mid-level Engineers)  

---

## Context

We operate a SaaS project management platform with **85,000 monthly active users (MAU)**, generating **~2 million tasks per month**. During peak business hours, our platform handles approximately **500 requests per second (req/s)**.

### Current Architecture
*   **Backend**: Python/Flask monolith (~50,000 lines of code).
*   **Database**: PostgreSQL (single primary instance with one read replica).
*   **Infrastructure**: 4 web servers behind an nginx load balancer, hosted on AWS.
*   **Cache**: Redis (currently utilized solely for session storage and rate limiting).
*   **Notifications**: Dispatched synchronously within the HTTP request-response cycle.

### The Problem
Processing notifications (emails, webhooks) synchronously inside the HTTP request cycle has led to critical production issues as our platform scales:
1.  **Request Timeouts**: Sending notifications blocks HTTP responses. Our average response latency has reached **800ms**, with spikes up to **8 seconds** during peak usage hours.
2.  **Silent Failures**: If our email provider (e.g., SendGrid) or a custom user webhook endpoint experiences downtime, notifications are silently dropped. The system lacks any retry mechanism or Dead-Letter Queue (DLQ).
3.  **Cascading Failures**: Due to synchronous blocking, slow external webhooks have twice caused database connection pool exhaustion this year, resulting in total downtime for unrelated features.
4.  **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") are treated identically to social notifications and are frequently dropped or lost, despite requiring strict delivery guarantees.

### Scaling Target & Objectives
*   **Decoupling**: Decouple the notification dispatch from the HTTP request-response cycle (asynchronous processing).
*   **Robustness**: Support automated retries with exponential backoff.
*   **Reliability**: Guarantee at-least-once delivery for billing events, and exactly-once processing where technically feasible.
*   **Real-time Capabilities**: Enable real-time WebSocket push notifications within 2 quarters.
*   **Growth**: Design the notification backbone to handle a **10x traffic growth** (equivalent to a peak of **5,000 req/s**) without requiring a re-architecture.

### Constraints
*   **Team Capacity**: A small team of **6 developers** (3 senior, 3 mid-level) with **no dedicated infrastructure/DevOps engineer**.
*   **Technology Stack**: The team already operates and monitors Redis in production.
*   **Experience**: There is **zero Apache Kafka experience** on the team.
*   **Timeline**: The solution must require **no more than 2 weeks** of setup, integration, and migration work before delivering demonstrable business value.
*   **Budget**: Extremely modest. Managed solutions like fully scaled Confluent Cloud are budget-prohibitive.
*   **Strict Semantics**: Exactly-once semantics must be maintained for billing-related notifications.

---

## Decision

We will use **Redis Streams** as our messaging backbone to decouple notifications from the HTTP request-response cycle, combined with application-layer idempotency implemented in **PostgreSQL** to guarantee exactly-once semantics for billing notifications.

### Justification

Redis Streams was chosen over Apache Kafka because it satisfies our technical throughput and reliability targets while aligning perfectly with our operational constraints. The decision is justified across the following six core technical dimensions:

#### 1. Operational Complexity
*   **Redis Streams (Winner)**: We already run Redis in production. No new infrastructure provisioning, security groups, or monitoring systems are needed. The operational overhead for our 6-person team is virtually zero.
*   **Apache Kafka**: Managing Kafka (requiring ZooKeeper or KRaft metadata management, JVM tuning, partition rebalancing, and careful disk provisioning) is notoriously complex. With no in-house Kafka expertise or dedicated infrastructure engineer, managing it ourselves would introduce significant risk. Managed alternatives are rejected due to budget constraints.

#### 2. Throughput & Latency
*   **Redis Streams (Winner)**: Redis operates in-memory and can comfortably handle over **100,000 operations per second** on a single core. Our 10x scaling target of **5,000 req/s** is well within the capabilities of a modest, single-node Redis instance.
*   **Apache Kafka**: Kafka is built for massive scale (millions of events per second) but is highly resource-intensive. It is fundamentally over-engineered for our 10x traffic projections and introduces high, unnecessary resource costs.

#### 3. Ordering Guarantees
*   **Redis Streams (Winner)**: Redis Streams guarantees absolute FIFO ordering natively. Every entry is appended with a monotonically increasing ID (by default `<timestamp>-<sequence>`, e.g., `1518713847000-0`). This ensures that notification events are processed in the exact order they are published.
*   **Apache Kafka**: Kafka guarantees ordering only *within a partition*. Maintaining strict global ordering across different partitions is complex and limits consumer parallelism.

#### 4. Message Retention & Durability
*   **Redis Streams (Winner)**: Redis Streams persistent structures are stored in memory for ultra-fast read/write access and can be configured to persist to disk via Append-Only Files (AOF) and RDB snapshots. We will implement stream capping (using the `MAXLEN` or `MINID` modifier during `XADD`) to prune processed events and bound memory usage, as we do not require infinite retention on our broker.
*   **Apache Kafka**: Kafka stores all messages on disk, enabling multi-gigabyte or infinite retention. While beneficial for event sourcing, this is unnecessary for a transient notification system, where we only need messages to persist until they are safely delivered and acknowledged.

#### 5. Consumer Groups
*   **Redis Streams (Winner)**: Redis Streams natively supports robust consumer groups (`XGROUP`, `XREADGROUP`). It manages offsets, tracks pending messages via Pending Entries Lists (PEL), and allows dead or slow consumers to be recovered by letting other consumers claim outstanding messages via `XCLAIM` and `XPENDING`. This is highly sufficient for building parallel, load-balanced workers to process webhooks and emails.
*   **Apache Kafka**: Kafka’s consumer groups are highly advanced but suffer from "rebalance storms" when consumers join or leave a group, which can halt message processing. In a dynamically scaling web application, this introduces a layer of operational failure modes that our team is ill-equipped to debug.

#### 6. Exactly-Once Semantics (EOS) & Billing
*   **Redis Streams & PostgreSQL (Winner)**:
    Achieving exactly-once delivery across external APIs (like SendGrid or custom webhooks) is a distributed systems problem that **cannot be solved by any message broker alone**. If a consumer successfully sends an email but crashes before acknowledging the message to the broker, the broker will redeliver the message, resulting in a duplicate email.
    To enforce exactly-once semantics for billing events, we must implement an **Idempotent Consumer** pattern backed by our database. We will:
    1.  Generate a unique notification UUID on the web server.
    2.  Use a **Transactional Outbox Pattern** to write both the business entity mutation and the notification event to a `notification_outbox` table in PostgreSQL in a single database transaction.
    3.  A publisher process reads from the database and writes to Redis Streams.
    4.  The consumer processes the message and records the processed UUID inside a unique-constrained table in PostgreSQL (e.g., `processed_notifications`) in a transaction before invoking the external side effect.
    Using this database-driven approach, we achieve robust, reliable exactly-once processing. Thus, Kafka’s native transactional capabilities do not offer a distinct advantage for this specific requirement.

---

## Consequences

Choosing Redis Streams carries significant architectural consequences.

### Pros (Benefits)
1.  **Immediate Time-to-Value**: Because Redis is already deployed, we can begin coding Python consumers immediately. A working prototype can be delivered to staging in under 3 days, easily satisfying our 2-week deadline.
2.  **No Additional Infrastructure Costs**: We leverage our existing Redis instance, keeping our infrastructure footprint light and budget-friendly.
3.  **Low Cognitive Overhead**: The Redis API is widely understood. Python client libraries (e.g., `redis-py`) are lightweight and integrate seamlessly into our Flask monolith.
4.  **Path to WebSockets**: Because Redis Streams allows multiple independent consumers/consumer groups to read from different offsets of the same stream, it serves as an excellent foundation for real-time WebSocket servers (planned for next quarter).

### Cons (Drawbacks & Risks)
1.  **In-Memory Boundedness**: Since Redis operates in-memory, an unmonitored consumer failure could cause the stream to grow indefinitely, leading to an Out-Of-Memory (OOM) crash that could bring down our session storage and rate limiter.
    *   *Mitigation*: We will strictly cap streams using `MAXLEN ~ 100000` (retaining a safe buffer of 100,000 historical notifications) and establish automated Datadog/CloudWatch alerts on Redis memory consumption.
2.  **Lacks Native Ecosystem Connectors**: Unlike Kafka Connect, which has pre-built connectors for external systems, we must write custom Python code to ingest and dispatch notifications.
    *   *Mitigation*: Given our Flask monolith architecture, custom Python workers are easy to write and maintain, and they provide complete flexibility over custom retry logic and error metrics.
3.  **No Native Broker-Side Transactional Joins**: Redis Streams cannot join streams or perform multi-stream transactions natively like Kafka's Streams API.
    *   *Mitigation*: Our business state resides in PostgreSQL. All transactional integrity is handled at the PostgreSQL layer, which is the industry standard for Flask monoliths.

---

## Alternatives Considered

### Apache Kafka (Rejected)
While Apache Kafka is the industry standard for large-scale event-driven architectures, we rejected it for the following reasons:
*   **Excessive Operational Overhead**: Managing Kafka would distract our 6-person engineering team from delivering core product value, requiring them to learn and operate a complex JVM-based stateful system.
*   **Violates Setup Timeline**: Provisioning Kafka, setting up security, configuring topic partition strategies, and learning the ecosystem would take significantly longer than 2 weeks, pushing back our time-to-value.
*   **Prohibitive Cost**: Managed services like AWS MSK or Confluent Cloud are out of reach for our modest budget.
*   **Over-engineered for Scale**: Our 10x peak projection of 5,000 req/s does not require the disk-bound streaming throughput of Kafka. Redis Streams handles this throughput effortlessly with a sub-millisecond footprint.
*   **Ecosystem Misalignment**: Python support for Kafka (via `confluent-kafka` or `kafka-python`) is significantly more complex to configure, debug, and mock in tests than Redis client libraries.
