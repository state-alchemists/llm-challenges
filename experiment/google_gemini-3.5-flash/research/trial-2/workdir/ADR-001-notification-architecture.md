# ADR-001: Selecting Redis Streams for the Notification Subsystem

## Status
Proposed

## Context
Our SaaS project management platform is experiencing critical performance and reliability issues due to our notification module sending emails and webhooks synchronously within the HTTP request cycle:
1. **Request Timeouts**: Sending notifications blocks HTTP responses. Average latency is 800ms, spiking to 8s during peak business hours (~500 req/s), causing timeouts for our 85,000 monthly active users.
2. **Silent Failures**: Webhook or email provider outages result in silently dropped notifications without retry mechanisms or Dead-Letter Queues (DLQs).
3. **Cascading Failures**: Slow webhook endpoints have exhausted PostgreSQL connection pools twice this year, taking down unrelated parts of the monolithic Python/Flask system.
4. **No Delivery Guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") have no delivery or idempotency guarantees.

We need to decouple notifications into an asynchronous processing pipeline that supports exponential backoff, at-least-once (exactly-once where feasible) delivery, and future WebSocket integration (within 2 quarters) while scaling for 10x traffic growth.

### Constraints
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure engineer**.
- **Current Stack**: Python/Flask monolith, PostgreSQL, and an existing Redis cluster used for session storage and rate limiting.
- **Experience**: Zero Apache Kafka experience on the team.
- **Timeline**: Must deliver value and go live in less than 2 weeks.
- **Budget**: Modest. Managed solutions like Confluent Cloud are cost-prohibitive at full scale.
- **Delivery Guarantee**: Must maintain exactly-once semantics for billing notifications.

---

## Decision
We choose **Redis Streams** as the underlying message broker for our new asynchronous notification subsystem.

### Justification

1. **Operational Complexity vs. Team Size**:
   With only 6 engineers and no dedicated infrastructure engineer, introducing Apache Kafka would impose an unsustainable "infrastructure tax." Kafka requires managing ZooKeeper/KRaft, tuning JVM parameters, designing partition strategies, and monitoring broker replication. Redis, however, is already running in our production environment. Selecting Redis Streams requires **zero additional infrastructure provisioning**, leveraging the team's existing operational knowledge and fitting perfectly within the strict **2-week delivery timeline**.

2. **Throughput and Scale**:
   Our current peak traffic is ~500 req/s. Even at our 10x scaling target (~5,000 req/s), a single Redis instance easily handles over 100,000 operations per second. Redis Streams operates entirely in-memory, delivering sub-millisecond read/write latencies that easily exceed our throughput needs without the overhead of disk-bound brokers.

3. **Exactly-Once Semantics (EOS) for Billing**:
   While Kafka offers "exactly-once semantics," this guarantee only holds within the Kafka boundary (producing and consuming between Kafka topics). Because sending emails and webhooks involves calling external, non-transactional third-party APIs (e.g., SendGrid, Mailgun, external user servers), **physical exactly-once delivery cannot be guaranteed by any message broker alone**.
   To solve this, we must implement the **Idempotent Consumer pattern** at the application level. By wrapping the email/webhook delivery in a PostgreSQL transaction that checks and records a unique idempotency key (e.g., `notification_uuid`), we guarantee that duplicate deliveries are safely ignored. Since application-level deduplication is mandatory under both architectures, Kafka's built-in transactional API provides no additional value for our external side-effects while adding massive complexity.

4. **Rich Consumer Group & Retry Semantics**:
   Redis Streams provides robust consumer group support (`XGROUP`, `XREADGROUP`) with offset tracking similar to Kafka. It automatically maintains a **Pending Entries List (PEL)** for each consumer. We can query the PEL using `XPENDING` and reclaim stalled messages via `XCLAIM`/`XAUTOCLAIM` to easily implement exponential backoff and route persistently failing messages to a Dead-Letter Queue (DLQ) in PostgreSQL.

5. **Real-time WebSocket Readiness**:
   Our scaling target includes adding real-time WebSocket push notifications within 2 quarters. Redis's native Pub/Sub and stream primitives are perfectly suited for routing events to WebSocket workers (e.g., via Flask-SocketIO or a lightweight Go/Node.js microservice) without introducing a separate event-distribution layer.

---

## Consequences

### Pros
- **Immediate Time-to-Value**: Implementation can begin immediately using standard Python libraries (e.g., `redis-py` or Celery with a Redis backend). Setup takes hours, not weeks.
- **Zero Cost Overhead**: No expensive licenses, managed cluster fees (e.g., Confluent Cloud), or additional AWS EC2 instance overhead.
- **Minimal Cognitive Load**: Developers are already familiar with Redis key-value operations; learning Redis Streams API is highly intuitive.
- **High Performance**: In-memory reads and writes eliminate disk-bound latency bottlenecks.

### Cons & Mitigations
- **In-Memory Volatility**: Redis stores data in RAM. A catastrophic crash could result in data loss if not configured correctly.
  - *Mitigation*: We will enable Append-Only File (AOF) persistence with `appendfsync everysec` and RDB snapshots on our existing Redis instance. For highly critical billing events, the Flask monolith will write the event to our persistent PostgreSQL database (acting as an Outbox) *before* publishing to Redis Streams.
- **Memory Growth & Storage Limits**: Unlike Kafka, which can store TBs of historical data on disk, Redis will exhaust RAM if stream lengths are unchecked.
  - *Mitigation*: We will use the `MAXLEN ~ 10000` option with `XADD` to cap stream sizes and automatically evict old notifications. Once a notification is processed or sent to the DLQ, its permanent audit log will reside in PostgreSQL, not Redis.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
1. **High Setup and Maintenance Overhead**: With zero Kafka experience on a 6-person team, setting up, securing, and tuning a production-ready Kafka cluster would take at least 4–6 weeks of dedicated engineering effort, violating our 2-week delivery constraint.
2. **Prohibitive Cost**: Managed options like Confluent Cloud are cost-prohibitive for our modest budget, and self-hosting Kafka on AWS (via MSK or EC2) carries high baseline instance costs even at low traffic volumes.
3. **Overkill for Our Scale**: At 500 req/s (or 5,000 req/s at 10x), Kafka's massive distributed scaling capabilities are unnecessary and introduce unwarranted complexity.
4. **Incorrect Fit for External Exactly-Once**: Kafka's transactional guarantees do not solve the external API delivery problem (emails/webhooks), which still requires the same application-level PostgreSQL deduplication we are implementing with Redis.
