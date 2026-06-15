# ADR-001: Selection of Redis Streams as the Notification Subsystem Broker

## Status
Proposed

## Context
Our SaaS project management platform currently services 85,000 monthly active users (MAU), processing approximately 2 million tasks per month. During peak business hours, our Flask backend on AWS experiences traffic spikes of up to ~500 requests per second (req/s). 

Currently, our notifications module (which sends emails and webhooks when tasks are updated, assigned, or completed) operates synchronously within the HTTP request cycle. As system load has scaled, this synchronous execution has caused critical operational issues:
1. **High Latency and Request Timeouts**: Blocking the HTTP response to execute network-bound notification tasks has increased average response latency to 800ms, with spikes up to 8 seconds during peak hours.
2. **Silent Failures**: Downstream email or webhook delivery failures result in notifications being silently dropped, as there are no retry mechanisms, dead-letter queues (DLQs), or delivery guarantees.
3. **Cascading Failures**: Connection pools have been exhausted twice this year due to slow third-party webhook endpoints, resulting in platform-wide outages of unrelated features.
4. **Lack of Delivery Guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") have no transactional safety or delivery guarantees.

### Scaling Target
To address these issues and prepare the platform for a 10x traffic increase (~5,000 req/s peak) without re-architecting, the notification subsystem must meet the following goals:
- **Asynchronous Decoupling**: Completely decouple the notification engine from the HTTP request cycle.
- **Reliable Retries**: Support automatic retry mechanisms with exponential backoff.
- **Delivery Guarantees**: Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- **Real-Time Push**: Facilitate the delivery of real-time WebSocket push notifications within the next two quarters.

### System Constraints
- **Team Size**: A small engineering team of 6 developers (3 senior, 3 mid-level) with no dedicated infrastructure/platform engineer.
- **Skillset**: No prior experience with Apache Kafka.
- **Timeline**: A maximum of 2 weeks of setup and migration overhead before delivering tangible production value.
- **Budget**: Extremely modest; we cannot afford costly managed services like Confluent Cloud at our projected scale.
- **Infrastructure Baseline**: We already run a Redis instance in production for session storage and rate limiting.

---

## Decision
We choose **Redis Streams** as the core messaging backbone for our notification subsystem. 

### Justification

Given our severe team constraints (6 engineers, no dedicated infrastructure support) and the 2-week delivery timeline, selecting **Redis Streams** represents the optimal balance of technical capability, speed-to-market, and long-term maintainability.

1. **Leveraging Existing Infrastructure**: We already deploy and operate Redis in production. Choosing Redis Streams avoids introducing a new piece of infrastructure to manage. This lowers the operational surface area to zero additional servers or complex clustering setups initially.
2. **Setup and Timeline Match**: Deploying Redis Streams is a native configuration change rather than a heavy infrastructure build. A Python-based worker pool reading from a Redis Stream via consumer groups can be fully written, tested, and deployed in less than 5 days, comfortably meeting our 2-week constraint.
3. **Throughput & Scalability to 10x**: A single Redis instance can easily handle tens of thousands of write operations per second, which easily accommodates our peak load of 500 req/s and our 10x future scaling target of ~5,000 req/s.
4. **Rich Consumer Group Semantics**: Redis Streams provides consumer group features (`XGROUP`, `XREADGROUP`) that track which consumer has been assigned a message. Crucially, it provides a Pending Entries List (PEL) via `XPENDING` and message claiming via `XCLAIM`, allowing us to construct a highly reliable, distributed consumer system with built-in retries for failed or crashed workers.
5. **Real-Time Push Synergy**: Redis’s in-memory speed makes it an excellent engine for WebSocket dispatch. The WebSocket service can subscribe directly to a stream or tap into Redis Pub/Sub, facilitating real-time UI pushes.

### Addressing Exactly-Once Semantics (EOS) for Billing
While Apache Kafka provides native transaction support, **true end-to-end exactly-once delivery across network boundaries (such as third-party mail API or webhook HTTP requests) is mathematically impossible at the transport layer alone** (due to the Two Generals' Problem). If a mail provider processes our request but our connection drops before receiving the HTTP 200 OK, any system will retry and duplicate the message.

Therefore, we will achieve **Exactly-Once Semantics (EOS)** at the **application layer** by pairing Redis Streams' **at-least-once delivery guarantees** with **idempotent consumers** backed by PostgreSQL:
- **At-Least-Once Delivery**: Consumers will not acknowledge (`XACK`) a message in Redis Streams until the side effect has successfully completed.
- **Idempotent Storage**: We will maintain a `processed_notifications` database table inside our primary PostgreSQL database.
- **Transactional Safety**: The worker will wrap the notification execution in a PostgreSQL transaction:
  ```sql
  -- Attempt to register the notification delivery attempt
  INSERT INTO processed_notifications (notification_id, status, processed_at)
  VALUES ('msg_abc123_billing', 'PROCESSED', NOW())
  ON CONFLICT (notification_id) DO NOTHING;
  ```
  If the insert succeeds (returning affected rows = 1), the notification side effect is executed (e.g., calling the Stripe billing email API). If it fails due to a unique key constraint, the worker knows this is a duplicate and silently acknowledges (`XACK`) the message in Redis without executing the side effect a second time.

This approach guarantees strict transactional consistency for billing-critical events while keeping the messaging broker simple and cheap.

---

## Consequences

### Pros
- **Zero Operational Setup Cost**: No new software to install, configure, cluster, monitor, or patch. We reuse our existing Redis infrastructure.
- **Sub-millisecond Latency**: Being an in-memory database, Redis Streams operates at sub-millisecond speeds, eliminating broker-side bottlenecks.
- **Rapid Time-to-Value**: The 6-person team can utilize standard, mature Python clients (like `redis-py`) to build out the consumer group and retry loop rapidly.
- **Built-In Delivery Tracking**: Redis keeps track of consumer group state, pending messages, and consumer failures via `XPENDING` and `XCLAIM`, allowing us to robustly handle worker crashes.
- **Capped Stream Memory**: We can use capped stream lengths (using `XADD stream MAXLEN ~ 100000`) to guarantee that memory usage is tightly bounded and does not grow indefinitely.

### Cons
- **In-Memory Volatility**: Redis is primarily an in-memory data store. If the Redis server crashes before data is written to disk, we risk message loss.
  - *Mitigation*: We will configure our production Redis with Append-Only File (AOF) persistence enabled (set to `appendfsync everysec`) and enable RDB snapshots for disaster recovery. Furthermore, billing-critical events will be stored in our durable PostgreSQL database as an "outbox" before being written to Redis Streams.
- **No Automatic Rebalancing**: Unlike Kafka, Redis Streams does not automatically re-distribute stream partitions when consumer instances scale up or down.
  - *Mitigation*: Since we operate a monolith backend, we can manually configure a fixed number of consumer workers per instance or split notifications into a few distinct streams (e.g., `streams:critical` and `streams:default`) to scale out processing.
- **Memory Scaling Overhead**: Since messages live in memory, keeping high volumes of historical messages in Redis Streams is unsustainable.
  - *Mitigation*: We will strictly use capping (`MAXLEN ~ 100000`) to evict historical processed messages. Historical audits of notifications will be persisted in PostgreSQL, leaving Redis Streams to function purely as an active transport medium.

---

## Alternatives Considered

### Apache Kafka

We seriously considered **Apache Kafka** as it is the industry standard for high-throughput, horizontally scalable event streaming. However, we rejected it for the following reasons:

1. **Extreme Operational Complexity**: Kafka requires running multiple brokers, ZooKeeper or KRaft metadata coordinators, configuring JVM runtimes, managing partition counts, and tuning replication factors. With a team of only 6 engineers and no dedicated infrastructure engineer, managing a self-hosted Kafka cluster would severely divert resources away from core product development.
2. **Prohibitive Financial Cost**: Managed Kafka solutions (such as Confluent Cloud) would relieve the operational burden, but their pricing model is too expensive for our modest budget, especially as we scale.
3. **Violated Timeline Constraints**: Installing, configuring, testing, and safely deploying a production-ready Kafka infrastructure would easily consume 3 to 4 weeks of dedicated engineering time, completely violating our 2-week limit for delivering value.
4. **Overkill for Current and Future Scale**: While Kafka scales to millions of messages per second, our peak scaling target is ~5,000 req/s. Redis Streams can effortlessly handle 50,000+ operations per second on a single, modest instance, meaning we do not need Kafka’s horizontal partition-scaling capabilities to meet our 10x target.
5. **No Experience**: The team has zero Kafka experience. This introduces an unacceptable operational risk of misconfiguration, which could cause partition lag, data loss, or system instability.
