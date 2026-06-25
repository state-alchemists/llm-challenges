# ADR-001: Notification Subsystem Architecture

- **Status**: Accepted
- **Date**: 2026-06-25
- **Deciders**: Engineering Team (3 Senior, 3 Mid-level Engineers)
- **Context Tags**: notifications, asynchronous-processing, redis, kafka, message-broker

## Context

We run a SaaS project management platform with **85,000 monthly active users**, creating approximately **2 million tasks per month**. During business hours, our system experiences a peak load of **~500 requests per second (req/s)**.

Currently, our technical stack consists of:
*   **Backend**: A Python/Flask monolith (~50,000 lines of code)
*   **Database**: PostgreSQL (single primary, one read replica)
*   **Infrastructure**: 4 web servers behind an Nginx load balancer hosted on AWS
*   **Cache**: Redis (currently used for session storage and rate limiting)

### Identified Problems
Our notifications module (which sends emails and webhooks when tasks are updated, assigned, or completed) is currently processed synchronously inside the HTTP request-response cycle. This has introduced critical problems:
1.  **Request Timeouts**: Sending notifications blocks HTTP threads, resulting in an average latency of 800ms, which spikes to 8,000ms during peak hours.
2.  **Silent Failures**: If an external email provider or third-party webhook endpoint is down, notifications are silently dropped without retries or Dead-Letter Queues (DLQ).
3.  **Cascading Failures**: Slow webhook targets have twice exhausted the backend PostgreSQL connection pool, taking down unrelated platform features.
4.  **No Delivery Guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") have no transactional or delivery guarantees, endangering revenue and compliance.

### Scaling & Architectural Targets
To resolve these issues and support our growth over the next 2 quarters, we must:
*   Decouple notifications from the HTTP thread pool via asynchronous worker processing.
*   Support retry mechanisms with exponential backoff and jitter.
*   Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
*   Add near-real-time WebSocket push notifications within 2 quarters.
*   **Handle 10x traffic growth without re-architecting** (i.e., scaling up to a peak of **5,000 req/s**).

### Constraints
*   **Team Capacity**: A small engineering team of 6 people (3 senior, 3 mid-level) with **no dedicated infrastructure/DevOps engineer**.
*   **Experience**: No Apache Kafka experience on the team today.
*   **Timeline**: The solution must not require more than **2 weeks of setup/migration work** before delivering production value.
*   **Budget**: Modest budget; cannot afford fully managed Kafka instances (e.g., Confluent Cloud) at full scale today.
*   **Pre-existing Tech**: Redis is already fully operational in our production environment.
*   **Safety**: Must maintain exactly-once processing guarantees for critical billing notifications.

---

## Decision

We will use **Redis Streams** as the primary message broker and stream-processing engine for our notification subsystem. 

### Justification

Redis Streams is selected because it satisfies all technical performance requirements while respecting our tight operational, timeline, and budgetary constraints.

1.  **Zero New Infrastructure & Low Complexity**: Because we already run Redis in production, we do not need to introduce, secure, or monitor a new infrastructure stack. We can leverage existing operational knowledge, avoiding the need for dedicated platform engineers.
2.  **Speed of Delivery (<2 Weeks)**: The team can implement Redis Streams immediately using the mature `redis-py` library. There is no steep learning curve, allowing us to hit the 2-week deadline easily.
3.  **High-Performance Headroom**: Since Redis operates in-memory, a single Redis instance can easily handle tens of thousands of read/write operations per second. Our 10x peak scaling target of 5,000 req/s will consume only a fraction of Redis's capacity, leaving plenty of headroom.
4.  **Native Stream Primitives for Reliable Delivery**: Redis Streams supports **Consumer Groups** via native commands (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`). This provides:
    *   **At-least-once delivery guarantees**: Messages remain in the Pending Entries List (PEL) until explicitly acknowledged with `XACK`.
    *   **Worker Fault Tolerance**: If a worker node crashes mid-processing, another worker can claim its stale pending messages via `XCLAIM`.
    *   **Dead-Letter Queue (DLQ)**: We can programmatically monitor PEL retry counts and route repeatedly failing messages to a separate `notifications:dlq` stream.
5.  **Achieving Exactly-Once Semantics (EOS) for Billing**:
    True end-to-end exactly-once semantics requires at-least-once delivery coupled with **idempotent consumption**. We will guarantee exactly-once processing by combining Redis Streams' at-least-once delivery with PostgreSQL's strong ACID properties:
    *   The Flask application generates a unique `notification_uuid` on task creation and appends it to the Redis Stream payload.
    *   The consumer processes the message inside a PostgreSQL transaction, attempting to insert the `notification_uuid` into a `processed_notifications` deduplication table.
    *   If the insert succeeds, the notification (email/webhook) is dispatched, the database transaction is committed, and `XACK` is sent to Redis.
    *   If the database insert fails due to a unique key violation (a duplicate delivery), the transaction is aborted, the notification is skipped, and the consumer simply acknowledges (`XACK`) the duplicate message to remove it from the stream.
    *   This database-level deduplication is simple, highly performant, and 100% robust against worker crashes.

---

## Consequences

### Pros (Positive Consequences)
*   **Minimal Operational Cost**: Leverages our existing AWS ElastiCache Redis infrastructure. Minimal base cost and zero Zookeeper/KRaft operational burden.
*   **Rapid Path to WebSocket Integration**: Because Redis includes native Pub/Sub, we can seamlessly reuse the same Redis cluster to broadcast real-time events to WebSocket servers when we build push notifications next quarter.
*   **Low Latency**: Appends (`XADD`) and reads (`XREADGROUP`) run in sub-millisecond times, completely eliminating HTTP connection pool bloat and Flask request timeouts.
*   **Robust Fault Tolerance**: The combination of `XPENDING` and PostgreSQL-backed idempotency prevents both silent failures and duplicate billing notifications.

### Cons (Negative Consequences)
*   **In-Memory Storage Limits**: Because Redis is in-memory, an accumulation of unconsumed notification payloads could exhaust RAM.
    *   *Mitigation*: We will enforce strict stream trimming during publishing using `XADD ... MAXLEN ~ 10000` (retaining the latest 10,000 notifications in the stream). Since notifications are consumed in real-time, long-term persistence in the broker is unnecessary; historical records remain safely persisted in PostgreSQL.
*   **Durability Trade-offs**: Redis persistence (RDB snapshots + AOF) is not as strictly guaranteed as Kafka's committed-on-disk logs. In a catastrophic multi-node hardware failure, up to 1 second of buffered notifications could be lost.
    *   *Mitigation*: We will configure Redis ElastiCache with Multi-AZ automatic failover and enable AOF with `appendfsync everysec`. In the worst-case scenario of a sub-second loss, billing notifications can be reconstructed or reconciled by querying PostgreSQL for un-sent statuses.

---

## Alternatives Considered

### Apache Kafka

Apache Kafka is a premier, disk-backed, highly durable distributed event streaming platform. We rejected Kafka for the following reasons:

*   **Prohibitive Operational Complexity**: Kafka requires Zookeeper or KRaft to coordinate brokers, custom JVM tuning, complex partition strategies, and specialized network configuration. Without a dedicated infrastructure engineer, our 6-person team would spend all their time managing Kafka instead of building product features.
*   **Failure of Time Constraints**: Setting up, securing, and testing a self-managed Kafka cluster on AWS (or setting up MSK) would require more than the allocated 2 weeks, delaying value delivery.
*   **High Financial Cost**: Small, managed Kafka deployments (such as Confluent Cloud) carry significant base pricing that exceeds our modest budget constraints.
*   **Accidental Architectural Complexity**: Kafka is built to handle millions of events per second and maintain multi-week message retention across distributed storage. Our system requires transient, low-latency queuing of up to 5,000 req/s. Using Kafka for this use-case is a classic example of over-engineering.

*We would have chosen Apache Kafka if:*
1.  Our throughput scaling target exceeded 100,000 req/s.
2.  We had a dedicated infrastructure/DevOps team to manage and monitor Kafka.
3.  We required long-term, multi-week replayable logs of historical events for analytics or event sourcing.
