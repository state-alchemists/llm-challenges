# ADR-001: Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-07-31
- **Deciders**: Engineering Team (3 Senior, 3 Mid-Level)
- **Context Tags**: notifications, redis, kafka, architecture, distributed-systems

## Context

We operate a SaaS project management platform with 85,000 monthly active users, generating approximately 2 million tasks per month, and experiencing peak traffic of ~500 requests per second during business hours. 

Our current architecture is a Python/Flask monolith (~50k lines of code) with a PostgreSQL database (one primary, one read replica). We already run Redis in production for session storage and rate limiting.

Notifications (emails and webhooks) are currently handled synchronously inside the HTTP request cycle. This has introduced several critical failure modes:
1. **Request Timeouts**: Notification delivery blocks the main thread. Average HTTP latency has risen to 800ms, spiking up to 8s during peak hours.
2. **Silent Drops**: Downstream failures of email providers or webhook endpoints lead to lost notifications. There is no retry mechanism, backoff policy, or Dead-Letter Queue (DLQ).
3. **Cascading Pool Exhaustion**: Slow webhook targets have caused PostgreSQL connection pool exhaustion on two occasions this year, taking down unrelated monolith features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") have no delivery guarantees, risking customer churn and revenue leakage.

### Scaling Target & Constraints
We must decouple notifications from the HTTP request cycle and build a system that supports retry with exponential backoff, guarantees at-least-once delivery for billing events (with exactly-once semantics where feasible), and prepares us to add real-time WebSocket push notifications within 2 quarters. The system must support a 10x traffic increase (~5,000 requests per second at peak) without requiring a future re-architecture.

The following constraints restrict our solution space:
* **Team Size**: 6 engineers (3 senior, 3 mid-level) with no dedicated SRE or infrastructure engineer.
* **Operational Familiarity**: The team has prior experience operating Redis in production, but possesses zero Apache Kafka experience.
* **Timeline**: The system must deliver production value within 2 weeks of starting setup.
* **Budget**: Modest. Managed Kafka (e.g., Confluent Cloud) is too expensive at our target scale, and we cannot afford dedicated infrastructure hires.

---

## Decision

We will use **Redis Streams** as the foundational message broker for the notification subsystem.

### Justification

1. **Zero Operational Overhead**: Since we already run and operate Redis in production, adopting Redis Streams requires zero new infrastructure provisioning, monitoring setup, or security compliance reviews. It perfectly fits our 6-person team's capacity.
2. **2-Week Time-to-Value**: Integrating Redis Streams into our Python/Flask monolith using standard libraries (such as `redis-py` or Celery with a Redis backend) can be prototyped, tested, and deployed within days, comfortably meeting the 2-week limit.
3. **Throughput and Scale Alignment**: Redis is an in-memory database capable of executing over 100,000 write operations per second on modest single-node instances. Our 10x scaling peak of 5,000 req/s is easily handled by our existing Redis setup, removing any immediate need for complex clustering.
4. **Native Consumer Group Capabilities**: Redis Streams natively supports consumer groups (`XGROUP`, `XREADGROUP`, `XACK`). This allows us to scale background worker processes horizontally and use the Pending Entries List (PEL) to track in-flight notifications, implement retries for crashed workers (via `XCLAIM`), and prevent silent message drops.
5. **Practical Exactly-Once Semantics via Idempotent Consumers**: True exactly-once delivery across network boundaries is mathematically impossible without cooperation between the broker, consumer, and downstream APIs (the "Two Generals" problem). If a worker successfully triggers an email API but crashes before acknowledging the broker, the email will be resent. 
   Therefore, exactly-once semantics for billing notifications must be enforced at the **application layer via consumer idempotency**. We will achieve this by recording unique notification event IDs within PostgreSQL transactions (e.g., using a `processed_notifications` table with a unique constraint) or leveraging Redis `SETNX` with a short TTL as a deduplication lock. Because this pattern is required regardless of the message broker, Kafka's native transactional APIs offer no practical advantage for our external API-integrating workers.
6. **WebSocket Synergy**: Redis possesses native Pub/Sub capabilities. Using Redis Streams for background jobs allows us to leverage the same Redis instance as a high-performance pub/sub backplane for real-time WebSocket connections (e.g., via Flask-SocketIO or a lightweight ASGI sidecar) when we implement WebSockets next quarter.

---

## Consequences

The decision to adopt Redis Streams carries the following trade-offs:

### Positive (Pros)
* **Immediate Developer Velocity**: The team can start writing producer and consumer code on day one using familiar tools and APIs.
* **Sub-Millisecond Ingestion Latency**: As an in-memory data store, Redis ingest latency is extremely low (typically < 1ms), minimizing the overhead added to our Flask HTTP request handlers.
* **Operational Cost Savings**: Avoids the significant financial overhead of managed Kafka services and the steep learning curve/hiring requirements of self-hosted message brokers.
* **Resilience to Downstream Outages**: Decoupling notifications protects our web servers from cascading connection pool exhaustion. Slow webhook endpoints will only slow down background consumers, not the HTTP monolith.

### Negative (Cons)
* **Memory Limits & Volatility**: Redis stores data in RAM. Uncapped streams can exhaust memory (OOM) and crash the server. We must strictly configure stream truncation using `XADD ... MAXLEN ~ 100000` to prevent memory bloat, meaning streams cannot serve as a permanent historical archive.
* **Short-term Retention**: Unlike Kafka, we cannot retain raw notification logs in the broker for weeks. Messages must be consumed, processed, and acknowledged promptly. Historical audit logs of notifications must be written to PostgreSQL rather than depending on stream replayability.
* **Data Loss Risk on Redis Failures**: While Redis supports Persistence (AOF and RDB), in-memory writes are asynchronously flushed to disk. A catastrophic Redis master crash before an AOF flush could lead to minor message loss. We accept this small risk for standard notifications, and will mitigate it for billing notifications by persisting billing events in PostgreSQL first (Transactional Outbox Pattern) before publishing them to Redis Streams.

### Follow-up Actions
1. **Outbox Pattern for Billing**: Implement a `pending_notifications` table in PostgreSQL. When a billing event occurs, write the event to PostgreSQL and commit it as part of the database transaction, then publish to Redis Streams. This guarantees at-least-once ingestion even if Redis experiences a rare crash.
2. **Monitoring & Alerting**: Configure alerts on Redis memory consumption and the size of the Pending Entries List (PEL) to detect stalled background workers.
3. **Truncation Strategy**: Standardize on a maximum stream length (e.g., 100,000 entries) for all notification topics to bound RAM usage.

---

## Alternatives Considered

### Apache Kafka

We rejected Apache Kafka for the following reasons:

1. **Unacceptable Operational Complexity**: Kafka requires significant effort to operate. Managing cluster configurations, replication factors, partition assignments, JVM tuning, and metadata (ZooKeeper/KRaft) is a full-time SRE role. With only 6 generalist developers, this would divert critical resources away from our core product.
2. **Prohibitive Cost**: Self-hosting Kafka securely on AWS EC2 across multiple availability zones is expensive, while managed alternatives like Confluent Cloud exceed our modest budget at our projected scale.
3. **Timeline Infraction**: Learning Kafka, configuring production-grade clusters, and integrating them with Python would take weeks or months. It would be impossible to deliver product value within the 2-week constraint.
4. **Throughput Overkill**: Kafka is designed for high-throughput log ingestion (millions of events/sec). Our current scale (500 req/s) and even our 10x target (5,000 req/s) are minor workloads that do not justify Kafka’s heavy infrastructure footprint.
5. **Redundant Exactly-Once Tooling**: Kafka's built-in transactions are complex to implement in Python and do not solve the problem of duplicate delivery to third-party webhooks/email providers. Since we must build application-level idempotency anyway, Kafka's core differentiator is neutralized for our notification system.
