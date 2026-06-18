# ADR-001: Selection of Redis Streams as the Notification Subsystem Message Broker

- **Status**: Accepted
- **Date**: 2026-06-19
- **Deciders**: Engineering Team (3 Senior, 3 Mid-level Engineers)
- **Context Tags**: messaging, notifications, redis, performance, architecture

---

## Context

Our SaaS project management platform currently serves 85,000 monthly active users (MAU), generating approximately 2 million tasks per month. Peak traffic reaches ~500 requests per second (req/s) during business hours.

### The Core Problem

Our current notifications module sends emails and webhooks synchronously within the HTTP request cycle. As traffic has grown, this synchronous design has introduced critical stability and performance issues:

1. **Request Timeouts**: Sending notifications blocks the client response. Average latency is 800ms, spiking to over 8 seconds during peak hours.
2. **Silent Failures**: If an email provider or external webhook endpoint experiences downtime, notifications are silently dropped. The system lacks retry mechanisms or Dead-Letter Queues (DLQs).
3. **Cascading Failures**: Connection pool exhaustion on our 4 web servers has occurred twice this year because of slow third-party webhook endpoints, causing complete outages for unrelated features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" or "payment failed") have no delivery guarantees, leading to revenue leakage and customer friction.

### Scaling Target and Architectural Goals

To support 10x traffic growth (~5,000 req/s peak) without re-architecting, we must satisfy the following:

- **Decoupled Processing**: Move notifications out of the HTTP request-response cycle into an asynchronous worker pipeline.
- **Resiliency & Retries**: Implement exponential backoff for failed webhook and email delivery attempts.
- **Reliability Guarantees**: Ensure at-least-once delivery for all notification events, and guarantee exactly-once processing for billing-critical events.
- **WebSocket Push**: Prepare the infrastructure to support real-time WebSocket push notifications within 2 quarters.

### Operational and Business Constraints

- **Team Size**: Only 6 engineers (3 senior, 3 mid-level) with no dedicated DevOps or infrastructure engineer.
- **Operational Experience**: The team has zero experience operating or development-hosting Apache Kafka.
- **Infrastructure Footprint**: We already run a Redis instance in production for session storage and rate-limiting.
- **Time-to-Value**: The setup, testing, and migration must be completed within 2 weeks.
- **Budget**: Modest budget constraints rule out premium managed messaging services like Confluent Cloud at our target scale.

---

## Decision

We will use **Redis Streams** as the message broker for our notification subsystem.

By leveraging the existing Redis infrastructure, we avoid introducing new platform components. Redis Streams natively supports consumer groups, which allows us to build a highly parallelized, resilient notification delivery pipeline. We will combine at-least-once delivery guarantees from Redis Streams with application-level idempotency to ensure exactly-once semantics for billing-critical events.

### Justification

Redis Streams perfectly satisfies all technical requirements while remaining within our strict operational constraints:

1. **Zero Infrastructure Overhead**: Reusing our existing production Redis instance ensures zero additional hosting costs and fits comfortably within our 2-week setup/migration timeline.
2. **More Than Sufficient Throughput**: Redis operates in-memory and can comfortably handle over 50,000 operations per second on modest hardware. Even at our 10x scaling target (peak ~5,000 req/s, translating to an estimated ~15,000 to ~25,000 notification events/s), a single Redis Streams instance easily handles the write and read throughput.
3. **Robust Consumer Group Mechanics**: Redis Streams provides consumer groups via `XGROUP`, `XREADGROUP`, `XACK`, and `XCLAIM`. This gives us the ability to horizontally scale Flask-based background workers, track pending (unacknowledged) messages via the Pending Entries List (PEL), and safely recover/retry failed deliveries.
4. **Guaranteed FIFO Ordering**: Redis Streams enforces strict, monotonically increasing sequence IDs (e.g., `<millisecondsTime>-<sequenceNumber>`) within each stream key. This guarantees that notifications for a specific task (such as "Task Created" followed by "Task Assigned") are processed in the correct order.
5. **A Direct Path to WebSockets**: Reusing Redis allows us to natively bridge our Streams consumer pipeline with Redis Pub/Sub to fan out real-time WebSocket push notifications in the next 2 quarters, avoiding the need for a separate integration layer.

---

## Consequences

Choosing Redis Streams commits us to specific operational boundaries and introduces distinct trade-offs:

### Positive (Pros)

- **Minimal Learning Curve**: The engineering team is already familiar with Redis. Writing consumers using Python's `redis-py` requires minimal training, allowing us to hit the 2-week delivery target.
- **Operational Simplicity**: No new servers to patch, secure, or monitor. We leverage existing AWS ElastiCache backup, replication, and clustering policies.
- **Ultra-low Latency**: Being in-memory, message publishing (`XADD`) takes sub-millisecond times, completely removing the notification latency from our HTTP request cycle.
- **Built-in Backoff/Retry Support**: The Pending Entries List (PEL) lets workers inspect unacknowledged messages (`XPENDING`), allowing us to easily build an application-level exponential backoff and retry scheduler.

### Negative (Cons)

- **RAM Constraints**: Unlike disk-based brokers, Redis Streams stores all messages in RAM. If our third-party email/webhook providers go down and notifications queue up, RAM usage could spike.
  - *Mitigation*: We will enforce stream capping using the `MAXLEN ~ 100000` argument on `XADD` to drop old messages once they are processed. We will also implement a Dead-Letter Queue (DLQ) in PostgreSQL for messages that exhaust their retry budget, freeing up Redis memory.
- **Durability Trade-off**: Under default configurations, Redis persistence (RDB snapshots and AOF) is not 100% durable in a complete power loss scenario.
  - *Mitigation*: For billing-critical notifications, we will implement the **Transactional Outbox Pattern**. The Flask monolith will write the billing event to PostgreSQL (our persistent source of truth) and the Redis Stream within the same database transaction. If Redis experiences a rare data loss event, we can safely re-ingest outstanding billing events from PostgreSQL.
- **No Automated Rebalancing**: Redis Streams does not automatically rebalance partitions among consumers when a consumer crashes or joins.
  - *Mitigation*: Workers will run a background thread that periodically calls `XPENDING` and uses `XCLAIM` to take ownership of messages that have been stuck in a "processing" state for longer than a specified visibility timeout (e.g., 30 seconds).

---

## Alternatives Considered

### 1. Apache Kafka

Apache Kafka was evaluated as the primary alternative. Kafka is an industry-standard, highly durable, disk-backed distributed event streaming platform.

- **Why it was rejected**: Kafka is too operationally complex and expensive for our team's current constraints. Operating a self-hosted Kafka cluster requires deep expertise in JVM tuning, ZooKeeper/KRaft quorum management, partition allocation, and disk-I/O monitoring. With only 6 engineers and no dedicated infrastructure support, self-hosting is a critical operational risk that would distract from product development. Managed options like Confluent Cloud were rejected because of our modest budget.
- **How we would have chosen Kafka**: We would have chosen Apache Kafka if our throughput requirements were 100x higher (>100,000 writes/s), if we required persistent event replayability spanning months/years, or if our team had a dedicated platform engineer to manage the infrastructure.

### Exactly-Once Semantics Comparison

| Feature / Guarantee | Redis Streams | Apache Kafka |
| :--- | :--- | :--- |
| **Throughput (10x Peak)** | Satisfies easily (~25k msg/s) | Over-provisions (>1M msg/s) |
| **Operational Effort** | Zero (reuses existing infrastructure) | Extremely high (requires cluster mgmt) |
| **Message Durability** | In-Memory (Optional RDB/AOF) | On-Disk (Multi-node replication) |
| **Setup Time** | < 3 days | > 2 weeks (plus monitoring setup) |
| **Exactly-Once Semantics** | Application-level deduplication required | Broker-level transactions (requires app-level deduplication anyway for external APIs) |

To maintain exactly-once semantics for billing notifications, **both** systems require application-level deduplication. Because our workers send notifications via external SMTP and webhooks, a network timeout during a third-party API call can cause duplicate deliveries regardless of broker-level transactions. Thus, Kafka's built-in transactions do not eliminate the need for application-level idempotency (e.g., saving message IDs/idempotency keys in PostgreSQL or Redis). Reusing Redis Streams with application-level idempotency achieves our safety goals without Kafka's operational burden.
