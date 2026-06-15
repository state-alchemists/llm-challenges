# ADR-001: Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-05-30
- **Deciders**: Engineering Team (3 senior, 3 mid-level)
- **Context tags**: notifications, event-streaming, queueing, scaling

## Context

We operate a SaaS project management platform experiencing rapid growth, currently supporting 85,000 monthly active users (MAUs), ~2 million tasks created per month, and peak traffic of approximately 500 requests per second (req/s) during business hours. 

Our current architecture consists of a Python/Flask monolith backend (~50k lines of code) with a PostgreSQL database (one primary, one read replica), 4 web servers behind an Nginx load balancer hosted on AWS, and a Redis instance used for session storage and rate limiting.

Currently, the notifications module—responsible for dispatching emails and webhooks when tasks are updated, assigned, or completed—runs synchronously within the HTTP request cycle. This has led to critical production issues:
1. **Request Timeouts**: Sending notifications blocks the response. Average request latency is 800ms, spiking to over 8s during peak hours.
2. **Silent Failures**: If external email providers or third-party webhook endpoints are down, notifications are dropped silently without retries or dead-letter queue (DLQ) logging.
3. **Cascading Failures**: Slow webhook endpoints have repeatedly caused connection pool exhaustion, resulting in major platform-wide outages of unrelated features.
4. **No Delivery Guarantees**: Critical billing-related notifications (e.g., "trial expired", "payment failed") have no delivery or ordering guarantees, causing lost revenue and customer friction.

To support our future product roadmap and scaling targets, the new notification subsystem must meet the following technical requirements:
* Decouple notification dispatching from the HTTP request cycle (fully asynchronous processing).
* Implement robust retry mechanics with exponential backoff.
* Support real-time WebSocket push notifications within 2 quarters.
* Handle a 10x traffic growth target (up to peak 5,000 req/s, ~20M tasks/month) without requiring a future architectural redesign.
* Maintain strict **exactly-once processing semantics** for billing-critical events, and guaranteed at-least-once delivery for general notifications.

However, the team operates under severe operational and budget constraints:
* **Team Size**: Only 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure/DevOps engineer.
* **Timeline**: Maximum of 2 weeks of setup and migration work before delivering production value.
* **Budget**: Modest budget; high-cost options like managed enterprise messaging platforms (e.g., Confluent Cloud) are unaffordable at scale.
* **Technology Stack**: No Kafka experience exists on the team today, whereas Redis is already operated in production for session storage and rate limiting.

## Decision

We will use **Redis Streams** as the messaging backbone of our asynchronous notifications subsystem. To guarantee exactly-once semantics for billing notifications, we will pair Redis Streams' at-least-once delivery with an application-level **PostgreSQL-backed idempotency and transaction boundaries layer**.

### Justification

1. **Zero Operational Bootstrapping & Skill Fit**: We already run Redis in production. Choosing Redis Streams avoids the steep learning curve and operational overhead of setting up and maintaining a completely new clustering technology (like Apache Kafka). With a small 6-person team and no dedicated DevOps engineer, minimizing the number of distinct technologies in our stack is paramount.
2. **Immediate Time-to-Value**: Because the team is familiar with Redis and standard Python client libraries (e.g., `redis-py`), we can implement a production-ready, consumer-group-based queuing system within a few days, comfortably meeting our tight 2-week migration deadline.
3. **Proven Scale and Performance**: Redis operates in-memory with sub-millisecond latencies. A single, modestly sized Redis instance can easily process 50,000+ operations per second. Our 10x peak traffic growth scaling target of 5,000 req/s represents less than 10% of Redis's single-node throughput limit, assuring us that Redis Streams can scale with us without requiring a re-architecture.
4. **Robust Queueing & Consumer Groups**: Redis Streams natively supports **Consumer Groups** (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`). This allows multiple Flask worker processes to cooperatively consume notifications, balance the load, and track message delivery status.
5. **Achieving Exactly-Once Processing Semantics**: True exactly-once delivery across unreliable networks is mathematically impossible without application-side coordination. We will achieve **exactly-once processing** for billing notifications by leveraging **At-Least-Once Delivery + Idempotent Processing**:
   * **At-Least-Once Delivery**: Handled natively by Redis Streams' consumer groups. If a worker fails or crashes while sending a notification, the message remains in the Pending Entries List (PEL) and is claimed and retried by another worker.
   * **Idempotent Processing via PostgreSQL**: Inside the Flask worker, we will wrap the notification processing within a PostgreSQL database transaction. We will check/insert a unique notification/event identifier (e.g. `event_id`) into a dedicated PostgreSQL table (`idempotency_keys`) using `INSERT ... ON CONFLICT DO NOTHING`. If the row insertion fails, the event is a duplicate and is skipped. If it succeeds, the worker dispatches the notification, commits the transaction, and executes `XACK` on Redis Streams to finalize.
6. **Future WebSocket Compatibility**: Redis's lightweight Pub/Sub and blocking read capabilities integrate perfectly with asynchronous networking libraries (like Gevent or ASGI uvicorn/gunicorn) for our upcoming real-time WebSocket push notifications.
7. **Cost-Efficiency**: Redis has a minimal footprint and can be self-hosted on a small AWS EC2 cluster or run via a cheap AWS ElastiCache instance. This fits our modest budget perfectly.

## Consequences

### Positive (Pros)
* **Immediate Delivery**: The solution will be delivered in under a week, resolving our blocking HTTP request timeouts and connection pool exhaustion issues immediately.
* **Ultra-Low Latency**: Offloading notifications to Redis Streams takes sub-millisecond execution time, keeping our Flask HTTP request latencies consistently low.
* **Operational Simplicity**: No new infrastructure components or JVM tuning required. We can monitor Redis using our existing tools.
* **Reliability and Backpressure**: Consumer groups natively distribute load across workers. Slow email/webhook endpoints will only back up the Redis queue, isolated entirely from the Flask HTTP pool.
* **Low Cost**: Negligible infrastructure expenditure.

### Negative (Cons)
* **In-Memory Data Volatility**: Unlike disk-backed brokers, Redis runs in memory. To mitigate the risk of message loss from unexpected Redis crashes, we must configure AOF (Append-Only File) persistence with `fsync everysec` (or `always` if necessary) on our dedicated messaging instance.
* **Manual Retry & DLQ Implementation**: Redis Streams does not provide out-of-the-box automatic exponential backoff or dead-letter queues. We must implement a lightweight Python wrapper that reads from the Pending Entries List (`XPENDING`), tracks retry counts, and moves repeatedly failing notifications to a dedicated DLQ stream (e.g. `notifications:dlq`) after $N$ attempts.
* **Memory Management & Stream Capping**: Unbounded streams will consume all Redis memory and crash the server. We must strictly enforce capped streams using the `MAXLEN ~ <size>` option (e.g., capping task streams to 100,000 entries) or actively delete/prune messages once they are fully acknowledged.

### Follow-up Action Items
1. **Dedicated Instance**: Spin up a dedicated Redis instance for messaging, separate from the ephemeral session cache/rate limiter, and enable AOF persistence.
2. **PostgreSQL Schema**: Create the `idempotency_keys` table with unique constraints on `event_id` and `event_type` to secure billing processing.
3. **Queue Wrapper Library**: Author a small Python wrapper for `redis-py` that handles `XADD`, `XREADGROUP`, consumer registration, and a custom exponential backoff retry loop with DLQ redirection.
4. **Monitoring**: Configure alerts for Redis memory usage, stream length, and the size of the pending entries list (PEL) to detect worker starvation early.

## Alternatives Considered

### Apache Kafka
* **Why Rejected**: While Apache Kafka is a powerful event-streaming platform with native disk storage, long-term retention, and robust exactly-once transaction features, it is a massive over-engineering for our scenario.
* **Key Drawbacks**:
  * **Operational Complexity**: Setup and maintenance of a ZooKeeper/KRaft quorum and Kafka brokers is highly complex. With a team of 6 and no DevOps engineer, we would drown in operational management.
  * **Time and Knowledge Gap**: With no Kafka experience, our 2-week migration constraint would be impossible to meet.
  * **Financial Overhead**: High hosting costs on AWS or premium fees for managed solutions like Confluent Cloud violate our modest budget constraints.
* **When it would have won**: We would have chosen Apache Kafka if our throughput requirements were 100x higher (e.g., >50,000 req/s), if we had a dedicated platform/infrastructure engineering team to manage it, or if we needed long-term, multi-week replayable event logs spanning several gigabytes or terabytes of historical events.
