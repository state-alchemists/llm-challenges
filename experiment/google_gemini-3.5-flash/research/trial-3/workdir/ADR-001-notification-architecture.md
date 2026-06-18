# ADR 001: Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-06-19
- **Deciders**: 6-Person Engineering Team (3 Senior, 3 Mid-level Engineers)
- **Context tags**: notifications, async-processing, redis, kafka, scaling

## Context

Our SaaS project management platform is experiencing severe degradation due to its synchronous notification system. Currently, notifications (emails, webhooks) are processed inline during the HTTP request cycle of our Python/Flask monolith. With 85,000 monthly active users and peak loads of ~500 req/s, this architecture has introduced major stability and performance issues:

1. **Request Timeouts**: Sending notifications blocks the client response. Average request latency has climbed to 800ms, with spikes up to 8 seconds during peak hours.
2. **Silent Failures**: Downstream failures (e.g., third-party email provider or slow consumer webhooks) result in lost notifications, as there is no retry logic or dead-letter queue (DLQ).
3. **Cascading Failures**: Unresponsive webhook endpoints have twice exhausted Flask's database connection pool, causing total platform outages.
4. **No Delivery Guarantees**: Critical billing notifications (such as trial expirations and payment failures) lack at-least-once delivery and deduplication mechanisms, risking user churn or revenue leakage.

### Scaling Target and Future Requirements

To support a projected **10x traffic growth** (up to 5,000 req/s peak) and ensure platform reliability, we must:
- Decouple notification dispatching from the HTTP request cycle using an asynchronous producer-consumer model.
- Implement reliable worker retries with exponential backoff and a robust Dead Letter Queue (DLQ).
- Provide at-least-once delivery guarantees for all events, and strict exactly-once semantics (EOS) for billing notifications.
- Deliver real-time WebSocket push notifications to users within the next two quarters.
- Deliver value in under **two weeks** without requiring a dedicated infrastructure engineer or expanding our modest budget.

---

## Decision

We will use **Redis Streams** to power our asynchronous notification subsystem.

We reject **Apache Kafka** for this implementation due to its high operational complexity, steep learning curve, significant infrastructure cost, and our lack of in-house Kafka expertise. Redis is already deployed and battle-tested in our production stack, making Redis Streams the most pragmatic, cost-effective, and high-performance solution that fits our strict two-week delivery constraint.

---

## Rationale

Our decision is justified by a direct technical comparison of both technologies against our operational and architectural constraints:

### 1. Operational Complexity vs. Team Capacity
- **Our Constraint**: A small 6-person team with no dedicated DevOps or platform engineer.
- **Redis Streams**: We already run Redis in production for session storage and rate limiting. Adopting Redis Streams introduces **zero new operational overhead**. The team is already familiar with Redis CLI, monitoring, and hosting on AWS.
- **Apache Kafka**: Kafka has a massive operational surface area. It requires setting up and maintaining ZooKeeper or KRaft coordination nodes, configuring JVM parameters, tuning garbage collection, monitoring disk usage, and managing partition reassignment. For a 6-person team, this would create an unsustainable maintenance burden, diverting scarce resources away from core product features.

### 2. Time-to-Value and Budget
- **Our Constraint**: Must deliver value within 2 weeks; modest budget (cannot afford managed Confluent Cloud at scale).
- **Redis Streams**: Since Redis is already provisioned, development can start on day one using the native Python client (`redis-py`). Setup, testing, and migration can easily be completed within the 2-week limit. There are **zero incremental infrastructure costs**.
- **Apache Kafka**: Spin-up time for a self-hosted, highly available (HA) Kafka cluster (minimum 3 brokers, 3 KRaft/ZooKeeper nodes for quorum) exceeds our 2-week timeline. Managed Confluent Cloud is cost-prohibitive under our current budget constraints.

### 3. Throughput and Scalability
- **Our Target**: Handle a 10x traffic increase to 5,000 req/s peak.
- **Redis Streams**: A single modest Redis instance (e.g., AWS ElastiCache `m6g.large`) can handle upwards of 50,000 write/read operations per second at sub-millisecond latencies. Because notifications represent a fraction of total requests, Redis Streams can easily handle our 10x peak load with negligible CPU and memory footprints.
- **Apache Kafka**: Kafka is engineered for multi-gigabyte-per-second pipelines and millions of events. While its performance is exceptional, it is massive over-engineering for our current and 10x scale requirements.

### 4. Consumer Groups and Reliability Guarantees
- **Redis Streams**: Natively supports consumer groups via the `XGROUP` and `XREADGROUP` APIs. Redis tracks active consumers, maintains read offsets, and provides a Pending Entries List (PEL) via `XPENDING`. If a Flask background worker crashes mid-execution, another worker can inspect the PEL and use `XCLAIM` to safely reclaim and process the message, guaranteeing at-least-once delivery.
- **Apache Kafka**: Kafka’s partition-rebalancing and consumer offsets are highly robust but complex to debug. Redis Streams' simpler PEL model is easier for our application developers to inspect and troubleshoot.

### 5. Message Retention and Durability
- **Redis Streams**: Redis operates primarily in-memory, backed by append-only persistence (AOF with `fsync=everysec`) and RDB snapshots. To prevent RAM exhaustion, we will use capped streams (e.g., appending with `XADD stream MAXLEN ~ 10000`). This is a perfect architectural fit for transient notification events that are consumed and acknowledged within seconds.
- **Apache Kafka**: Kafka persists all messages to disk, allowing indefinite retention and historical replay. However, our notifications do not require historical event replays; once sent, they are permanently archived in PostgreSQL. Paying a steep operational and storage premium for disk-based log replay is unjustified.

### 6. Achieving Exactly-Once Semantics (EOS) for Billing
While Kafka offers native transactions and idempotent producers, **true end-to-end exactly-once delivery across external networks (e.g., sending emails via SendGrid or hitting customer webhooks) is mathematically impossible** without receiver-side deduplication. A worker could crash *after* calling the external API but *before* committing the offset to Kafka/Redis, resulting in a duplicate send upon retry.

We will enforce robust, application-level Exactly-Once Semantics in Python/Flask using our existing PostgreSQL DB:
1. **Idempotency Keys**: For billing events, the Flask producer generates a unique `notification_uuid` and stores it alongside the event payload inside PostgreSQL within the database transaction.
2. **At-Least-Once Dispatch**: The event is pushed to Redis Streams.
3. **Deduplication on Consumer**: The background worker processes the event inside a PostgreSQL transaction, inserting the record into a `sent_notifications` table with a `UNIQUE` constraint on the `idempotency_key`.
   - If a duplicate message is delivered (due to a previous worker crash or timeout), the unique constraint triggers a `UNIQUE VIOLATION`, and the consumer safely performs a `DO NOTHING` (discarding the duplicate) and sends an `XACK` to Redis to clear the PEL.

### 7. WebSocket Integration (2-Quarter Horizon)
- **Redis Streams**: Fits perfectly with our real-time WebSocket push goal. Redis has a built-in Pub/Sub engine, which is the industry-standard backplane for scaling real-time WebSocket servers (e.g., scaling `Flask-SocketIO` or custom gevent workers across multiple nodes). The notification worker can publish successful dispatches to a Redis Pub/Sub channel, which WebSocket nodes instantly relay to connected clients.
- **Apache Kafka**: Bridging Kafka directly to WebSockets requires an additional proxy layer or complex custom consumers, increasing system complexity.

---

## Consequences

### Positive (Pros)
- **Immediate Time-to-Value**: Sub-2-week implementation is fully realistic.
- **Simplified Operational Stack**: Zero new infrastructure dependencies. Leverages our existing, well-understood Redis cluster.
- **Sub-Millisecond Performance**: Extremely fast queueing latency, liberating Flask request threads instantly.
- **Real-time WebSockets Ready**: Seamless integration with Redis Pub/Sub to scale real-time WebSocket pushes.
- **Highly Reliable Retries**: The consumer group PEL enables safe, persistent worker crash recovery.

### Negative (Cons)
- **Memory Footprint**: Redis Streams consume RAM. We must enforce stream capping (`MAXLEN` or `MINID`) to prune processed logs, meaning we cannot use Redis Streams as a long-term audit trail.
- **Operational Durability Trade-off**: Under an catastrophic AWS hardware failure where the primary Redis node loses power before writing to disk, up to 1 second of transient notification messages could be lost (due to `fsync=everysec`). We accept this minor risk for general notifications, mitigated by logging critical billing state in PostgreSQL before dispatching.
- **Development Overhead**: Redis lacks pre-built ecosystem connectors (unlike Kafka Connect). We must write custom Python logic for exponential backoff, dead-letter routing, and PG-based deduplication.

### Follow-ups and Next Steps
1. **Producer Integration**: Modify the Flask HTTP request paths to write notification events to Redis Streams via `XADD` instead of invoking mail/webhook clients synchronously.
2. **Worker Implementation**: Write a lightweight Python worker daemon utilizing `redis-py` to read from the stream via `XREADGROUP`, process tasks, handle PG transactions, and acknowledge via `XACK`.
3. **Stream Pruning**: Enforce `MAXLEN ~ 50000` with approximate capping (`~`) on all `XADD` operations to keep RAM usage predictable.
4. **DLQ Logic**: Implement a "poison pill" counter. If a message fails processing more than 5 times (based on `XPENDING` retry counts), the worker will log a critical error, publish the message to a dedicated `notifications:dlq` Redis stream, and call `XACK` on the main stream to prevent infinite consumer loops.

---

## Alternatives Considered

### 1. Apache Kafka
- **Why we rejected it**: Operating a production-grade, highly-available Kafka cluster requires a minimum of 3 brokers and 3 ZooKeeper/KRaft instances, which is cost-prohibitive for our budget. Without a dedicated infrastructure engineer, managing partition configurations, network partitions, and JVM sizing would overwhelm our 6-person team. The learning curve makes a 2-week implementation impossible.
- **What would have made Kafka win**: If our team already had Kafka operational experience, if we had a dedicated platform engineer, or if our event volume were orders of magnitude higher (e.g., >100,000 events/sec tracking granular user clickstreams), the overhead of Kafka would be justified.

---

## Backlinks

- [System Context](system_context.md) — Architectural requirements and constraints described here.
