# Title: ADR-001 - Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform has grown to 85,000 monthly active users and ~2M tasks created per month. Peak traffic reaches ~500 req/s during business hours. 

Currently, notifications (emails and webhooks for task updates, assignments, and completions) are handled synchronously within the HTTP request cycle of our Python/Flask monolith. This has caused severe issues:
1. **Request Timeouts**: Sending notifications blocks the response. Average response latency is 800ms, spiking to 8s during peak hours due to network calls to third-party email providers and webhooks.
2. **Silent Failures**: If an email provider or webhook endpoint is down, the notification is silently dropped with no retries or dead-letter queue (DLQ).
3. **Cascading Failures**: Connection pool exhaustion has occurred twice this year because of slow external webhook endpoints, taking down unrelated features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" and "payment failed") have no delivery guarantees and must be delivered exactly once.

### Scaling Targets & Requirements
- **Decouple Notifications**: Move notification delivery out of the HTTP request cycle into asynchronous workers.
- **Durability & Retries**: Support automatic retries with exponential backoff and dead-letter queues.
- **Delivery Guarantees**: Ensure at-least-once delivery for billing events, and exactly-once semantics where feasible.
- **WebSocket Push**: Add real-time WebSocket push notifications within 2 quarters.
- **10x Scalability**: Handle 10x traffic growth (up to 5,000 req/s) without re-architecting.

### Constraints
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure/DevOps engineer.
- **Current Infrastructure**: Python/Flask monolith on AWS (4 web servers behind Nginx), PostgreSQL (primary + read replica), and Redis (used for session storage and rate limiting today).
- **Team Experience**: Zero Apache Kafka experience on the team.
- **Timeline**: Must deliver value in less than 2 weeks of setup/migration work.
- **Budget**: Modest. Managed Confluent Cloud is too expensive at full scale, and self-hosting Kafka is cost-prohibitive.
- **Exactly-Once for Billing**: Must guarantee exactly-once execution/delivery for critical billing notifications.

---

## Decision
We choose **Redis Streams** as the technology for our notification subsystem. 

### Justification

1. **Operational Simplicity**: 
   Our 6-person team has no dedicated infrastructure engineer. We already run Redis in production for session storage and rate limiting. Choosing Redis Streams introduces zero new infrastructure overhead, whereas running or learning Kafka from scratch is operationally risky.
2. **Timeline (Within 2 Weeks)**: 
   Integrating Redis Streams with Python is straightforward using the existing `redis-py` library. The team can design, implement, test, and deploy a production-ready solution within days. Implementing Kafka, configuring partition/replication schemes, and tuning broker JVMs would take weeks of research and setup, violating our 2-week constraint.
3. **Performance and Throughput**: 
   Redis Streams operates in-memory, delivering sub-millisecond write and read latencies. While our current peak is 500 req/s, our 10x scaling target is 5,000 req/s. A single, modest Redis instance can easily process over 50,000 stream operations per second, comfortably handling our 10x scaling targets and beyond.
4. **Robust Consumer Groups**: 
   Redis Streams has built-in consumer groups (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`). This allows us to run worker processes across our 4 AWS application servers that cooperatively consume notifications. It provides automatic offset/message tracking, letting us monitor which consumer has claimed a message, which are pending, and when they are acknowledged.
5. **Ordering Guarantees**: 
   Redis Streams guarantees strict FIFO ordering within a stream. Each message is assigned a unique, monotonically increasing ID based on the timestamp (e.g., `1518951480106-0`). This ensures that sequential notification states (e.g., "Task Assigned" followed by "Task Completed") are processed in the correct order.
6. **Exactly-Once Semantics (EOS)**: 
   While Apache Kafka offers native broker-level transactional EOS, this guarantee does not extend to external network boundaries (such as calling SendGrid or a customer webhook). If a network timeout occurs after our worker sends an email but before it commits the offset, the notification will be resent, violating exactly-once delivery. 
   Therefore, exactly-once delivery must be achieved via **at-least-once delivery with application-level deduplication**. 
   - **At-Least-Once Delivery**: Redis Streams natively supports this. Workers read messages with `XREADGROUP`, and if a worker crashes before calling `XACK`, the message remains in the Pending Entries List (PEL). A supervisor process can query the PEL with `XPENDING` and re-assign the message using `XCLAIM`.
   - **Application-Level Deduplication**: Consumers will wrap the notification processing and PostgreSQL updates in a transaction. We will maintain a `processed_notifications` table in PostgreSQL. Before sending a billing notification, the consumer will attempt to insert the notification's unique UUID with a `UNIQUE` constraint. If the insert succeeds, the notification is sent and the transaction is committed. If it fails due to a constraint violation, the message is acknowledged and skipped, achieving robust exactly-once semantics.

---

## Consequences

### Pros (Positive Consequences)
- **Zero Additional Infrastructure & Costs**: No new servers, cluster licenses, or managed platform costs. We leverage our existing Redis deployment, keeping cloud spend to a minimum.
- **Low Learning Curve**: The API for Redis Streams is simple and intuitive. The 6-person team can master it immediately without learning complex concepts like Kafka partition rebalancing or Zookeeper/KRaft quorum management.
- **Immediate Value**: High likelihood of beating the 2-week migration deadline and stabilizing the production monolith quickly.
- **Flexible Scaling**: When WebSocket push notifications are introduced in 2 quarters, we can easily feed them from a dedicated Redis stream without adding specialized publish/subscribe brokers.
- **In-Memory Speed**: Sub-millisecond queuing latency prevents message broker bottlenecks from affecting web application response times.

### Cons (Negative Consequences)
- **Memory-Bounded Retention**: Since Redis is an in-memory database, keeping history in streams consumes RAM. We must enforce strict stream capping (using `XADD` with `MAXLEN ~ 100000` or `MINID`) to prevent memory exhaustion. Long-term notification history must be stored in PostgreSQL, not Redis.
- **Durability Trade-off**: Redis persistence (RDB snapshots or AOF) is asynchronous by default (`appendfsync everysec` to maintain high performance). If the Redis server crashes catastrophically, we could lose up to 1 second of stream data. 
  - *Mitigation*: For billing-critical notifications, we will write the notification log to PostgreSQL (primary DB with synchronous replication) within the HTTP transaction first, and then publish to the Redis Stream. If Redis crashes, a cron job can reconcile missing items from the PostgreSQL log.
- **Lack of Advanced Wildcard Routing**: Unlike RabbitMQ or Kafka, Redis does not have built-in topic exchange patterns or wildcard-based partition routing. We must explicitly define stream keys (e.g., `stream:notifications:billing` and `stream:notifications:transactional`) to route messages to appropriate consumer groups.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
- **Excessive Operational Complexity**: Kafka has a steep learning curve and high operational surface area. It requires setting up and maintaining ZooKeeper or KRaft metadata servers, managing multiple brokers for high availability, configuring partition keys, and tuning JVM garbage collection. With a 6-person team and no infrastructure engineer, self-hosting is a major operational risk.
- **Prohibitive Costs**: Managed Kafka (Confluent Cloud) is cost-prohibitive for our modest budget at our projected scale. Running a self-hosted, highly available 3-broker cluster on AWS is similarly expensive and wasteful given our relatively low throughput requirements.
- **Violation of Time Constraints**: The team has no Kafka experience. Developing the integration, learning consumer group mechanics (rebalancing, commit offsets), and setting up the infrastructure would take 4 to 6 weeks, which directly violates the 2-week limit.
- **Over-engineered for Scale**: While Kafka is designed to process millions of events per second, our 10x target of 5,000 req/s is easily handled by Redis. Kafka is massive overkill for a startup of our current size.
- **EOS Misconception**: Kafka’s transactional exactly-once capabilities only apply within the Kafka broker ecosystem itself. Because sending notifications requires calling external HTTP endpoints, we would still need to build application-level deduplication (idempotency) to protect against network timeouts. Thus, Kafka's native EOS does not solve our primary boundary problem, making its complexity unjustified.
