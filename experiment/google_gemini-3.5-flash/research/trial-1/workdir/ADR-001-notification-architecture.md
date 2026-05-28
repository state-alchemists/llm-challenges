# ADR 0001: Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-05-28
- **Deciders**: Engineering Team (3 Senior, 3 Mid-Level Engineers)
- **Context tags**: architecture, notifications, queuing, storage, redis, kafka

## Context

We run a B2B SaaS project management platform with 85,000 monthly active users (MAU), handling approximately 2 million task creations per month and experiencing peak traffic of ~500 requests per second (req/s) during business hours. 

Our current architecture is a Python/Flask monolith backed by a single PostgreSQL primary instance (with one read replica). To date, all transactional, webhook, and email notifications (such as assignment alerts, task updates, and payment alerts) are handled synchronously within the HTTP request-response cycle. This setup has introduced severe production issues:
1. **Request timeouts**: Sending notifications blocks HTTP responses. Average endpoint latency is 800ms, spiking to 8s during peak traffic.
2. **Silent failures**: If email/webhook services are unreachable, notifications are dropped without retry mechanisms or dead-letter queues (DLQs).
3. **Cascading failures**: Downstream delays (e.g., slow recipient webhooks) have exhausted our web server connection pool twice this year, taking down unrelated monolith features.
4. **No delivery guarantees**: Critical events, particularly billing-related notifications (e.g., "payment failed", "trial expired"), lack delivery guarantees.

### Scaling Targets & Requirements
- **Decoupling**: Move notifications out of the synchronous HTTP request-response cycle into an asynchronous processing pipeline.
- **Resilience**: Implement exponential backoff and retry mechanisms for webhook/email dispatch.
- **Delivery Guarantees**: Ensure at-least-once delivery for general notifications, and achieve exactly-once semantics (EOS) for billing notifications.
- **WebSocket Push**: Integrate real-time WebSocket push notifications within 2 quarters.
- **Scale**: Must comfortably support a 10x traffic increase (~5,000 req/s peak) without requiring an immediate architectural overhaul.

### Constraints
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with zero dedicated infrastructure/DevOps engineers.
- **Prior Experience**: The team has zero operational or development experience with Apache Kafka.
- **Existing Footprint**: We already run and maintain Redis in production for session storage and rate limiting.
- **Timeline**: We must deliver value (the decoupled notification pipeline) in under 2 weeks.
- **Budget**: Modest. We cannot afford managed options like Confluent Cloud at scale.

---

## Decision

We will use **Redis Streams** as the core messaging engine for the notification subsystem.

We reject Apache Kafka because its high operational complexity and resource demands directly violate our timeline, team size, and budget constraints. Redis Streams provides the necessary features—at-least-once delivery, consumer groups, ordering guarantees, and low latency—using our existing infrastructure and with minimal learning overhead.

### Technical Justification & Evaluation of Properties

#### 1. Operational Complexity & Team Constraints
Our 6-person team has no dedicated infrastructure engineer and zero prior Kafka experience. Setting up, tuning, securing, and maintaining a self-hosted Apache Kafka cluster (using either ZooKeeper or KRaft) is highly complex, requiring significant ongoing engineering attention. Managed Kafka options (such as Confluent Cloud) violate our modest budget constraints. 
In contrast, we already run, monitor, and back up Redis in production. Utilizing **Redis Streams** requires zero new infrastructure setup, zero additional license or hosting fees, and fits seamlessly into our existing operational processes. The API is straightforward, allowing our team to design, implement, test, and deploy the new pipeline within the mandated 2-week window.

#### 2. Throughput & 10x Scalability
Our current peak is ~500 req/s, and our 10x scaling target requires supporting ~5,000 req/s. 
A single, moderate-spec Redis node can easily process over 50,000 to 100,000 write operations per second. Since Redis operates fully in-memory, processing 5,000 req/s for notifications is well within the capabilities of a single standard Redis instance. We can handle our 10x growth targets comfortably on a single instance without the overhead of horizontal partitioning, sharding, or complex cluster topologies.

#### 3. Ordering Guarantees
Notifications must preserve ordering to avoid race conditions (e.g., a "task completed" notification must not arrive before a "task created" notification). 
Redis Streams guarantees strict, FIFO ordering within each stream. Message IDs are structured as `<millisecondsTime>-<sequenceNumber>` (e.g., `1626349200000-0`), which are strictly monotonically increasing. Consumers reading from a stream are guaranteed to receive events in the precise order they were appended.

#### 4. Message Retention & Memory Management
Because notifications are transient (they are consumed, dispatched, and then discarded or stored in PostgreSQL for historical auditing), long-term retention on the broker is unnecessary. 
Kafka persists messages to disk indefinitely (or based on size/time limits), which adds disk-I/O overhead. Redis Streams operates in-memory but supports efficient retention capping. We will write to our streams using the `MAXLEN ~ 10000` (approximate capping) option or the `MINID` trimmer. This keeps Redis’s memory footprint strictly bounded and prevents out-of-memory (OOM) errors, while PostgreSQL serves as our durable system of record for notification delivery logs.

#### 5. Consumer Groups & Failure Recovery
To prevent duplicate processing while distributing the workload, we need to partition consumer processing. 
Redis Streams natively supports Consumer Groups via the `XGROUP` and `XREADGROUP` commands. This allows multiple concurrent workers (implemented as background Python processes) to coordinate:
- **Load Balancing**: Each message is delivered to only one consumer in the group.
- **At-Least-Once Delivery via ACKs**: Messages remain in a Pending Entries List (PEL) until acknowledged with `XACK`.
- **Fault Tolerance**: If a consumer crashes mid-processing, other consumers can inspect the PEL using `XPENDING` and claim the dead consumer's unacknowledged messages using `XCLAIM` to retry dispatching.

#### 6. Exactly-Once Semantics (EOS) for Billing
Achieving true end-to-end exactly-once delivery when communicating with external networks (such as sending emails or webhooks) is mathematically impossible due to the Two Generals' Problem (network partitions can cause timeouts during ACKs, leading to retries). 
To achieve effective exactly-once delivery for critical billing events, we will implement the **Idempotent Consumer Pattern** at the application layer:
- The Flask application will generate a unique UUID (`notification_id`) for every event and embed it in the Redis Stream message.
- The consumer worker will process each message inside a PostgreSQL database transaction. It will insert the `notification_id` into a `processed_notifications` table with a unique constraint.
- If a message is redelivered (due to a consumer crash before `XACK` or network retry), the database constraint will trigger a duplicate key violation, allowing the worker to safely ignore the redelivered message and call `XACK` immediately.
Redis Streams' at-least-once delivery (tracked via PEL and `XACK`) serves as the robust foundation for this application-level idempotency, matching the reliability of Kafka’s transactional producer/consumer loop for our external integration use case.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
- **Operational Overhead**: Setting up and running Kafka requires configuring brokers, managing partitions, tuning JVM garbage collection, and managing ZooKeeper or KRaft metadata. This violates our constraint of having no dedicated infrastructure engineer.
- **Resource Intensity**: Kafka requires substantial RAM and CPU even at idle to run JVM processes, which would increase our hosting budget significantly compared to our existing, lightweight Redis footprint.
- **Steep Learning Curve**: With zero Kafka experience on a team of 6, developing secure producers/consumers, configuring replication factors, handling rebalances, and implementing poison-pill mitigation would require months of learning, violating our strict 2-week timeline.
- **Unnecessary Capabilities**: Kafka's primary strengths—such as infinite disk retention, replayability of logs from arbitrary offsets, and massive multi-gigabyte throughput—are overkill for our transient, low-latency notification requirements.
- **WebSocket Suitability**: Real-time push notifications are easier to orchestrate with Redis due to its native, sub-millisecond, memory-centric pub/sub and streaming capabilities, whereas Kafka's polling-based model introduces higher baseline latencies.

*We would have chosen Apache Kafka only if our throughput requirements were 100x higher (>100,000 req/s), if our data required permanent broker-side disk persistence, or if we had a dedicated platforms/infrastructure team to absorb the operational burden.*

---

## Consequences

### Positive (Pros)
- **Zero New Infrastructure**: Leverages our existing, battle-tested production Redis instance, keeping hosting costs flat and deployment pipelines unchanged.
- **Rapid Time-to-Value**: The simple Redis Streams API allows the team to deliver the working decoupled pipeline within the 2-week deadline.
- **Robust Delivery**: Native consumer groups, PEL tracking (`XPENDING`), and claiming (`XCLAIM`) guarantee at-least-once delivery and make the system resilient to worker crashes.
- **Low Latency & High Performance**: Sub-millisecond stream writes remove latency from the Flask HTTP cycle, dropping average response times from 800ms+ to <20ms.
- **WebSocket Readiness**: Redis’s low-latency memory architecture seamlessly supports our upcoming real-time WebSocket push engine.

### Negative (Cons)
- **In-Memory Limits**: Since Redis is an in-memory database, we must carefully bound stream lengths (`MAXLEN ~ 10000`). If we experience a prolonged consumer outage and do not cap streams, Redis could run out of memory, risking eviction or system instability.
- **Data Loss Risk on Crash**: By default, Redis is configured with asynchronous persistence. If the Redis server crashes before persisting stream appends to disk, a small window of messages could be lost. We must mitigate this by enabling AOF (Append Only File) persistence with `appendfsync everysec`.
- **No Native DLQ**: Redis Streams does not have an out-of-the-box Dead Letter Queue (DLQ) feature. We must implement our own retry tracking in the consumer code and push exhausted messages to a separate dedicated Redis stream (e.g., `notifications:dlq`) after $N$ failed attempts.

### Follow-ups (Next Steps)
1. **Enable Redis AOF**: Configure our production Redis instance with `appendfsync everysec` to ensure durable stream logging without incurring a significant write performance penalty.
2. **Implement Monolith Stream Producer**: Integrate the `redis-py` library into the Flask monolith to write serialized notification payloads (with generated `notification_id` UUIDs) to Redis Streams during task updates.
3. **Build Idempotent Python Consumer**: Implement background worker processes in Python utilizing `XREADGROUP`, `XPENDING`, `XCLAIM`, and a PostgreSQL deduplication table to guarantee exactly-once execution.
4. **Configure Monitoring**: Set up Datadog/CloudWatch metrics to monitor Redis memory usage and stream length, triggering alerts if stream depths exceed safety thresholds.

---

## Backlinks
- [System Context: Notifier Subsystem Decision](system_context.md)
