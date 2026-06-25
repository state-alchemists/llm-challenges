# ADR-001: Notification Subsystem Architecture

- **Status**: Accepted
- **Date**: 2026-06-25
- **Deciders**: Zaruba (Lead Architect), Engineering Team (6 members)
- **Context tags**: architecture, notification-subsystem, redis-streams, kafka, asynchronous-processing

## Context

We operate a SaaS project management platform with 85,000 monthly active users (MAU), processing approximately 2 million task creations per month, and facing a peak load of ~500 requests per second (req/s) during business hours. 

Our current notification subsystem (sending emails and webhooks for task updates, assignments, and completions) is executed synchronously within the Python/Flask HTTP request cycle. As traffic has scaled, this synchronous design has introduced critical failures:
1. **Request Timeouts**: Sending notifications blocks the HTTP response, driving average latency to 800ms and peak latency spikes up to 8s.
2. **Silent Failures**: The absence of retries or a dead-letter queue (DLQ) means notifications are permanently lost if third-party email providers or webhook endpoints go down.
3. **Cascading Failures**: Unresponsive external webhook endpoints have twice caused connection pool exhaustion, bringing down unrelated parts of the monolith.
4. **No Delivery Guarantees**: Critical billing-related notifications (e.g., "trial expired", "payment failed") are sent without delivery guarantees, resulting in lost revenue or unnotified account states.

### Scaling Target & Objectives
We need to refactor the architecture to support:
- Decoupling notifications from the HTTP thread pool (asynchronous processing).
- Retries with exponential backoff and dead-letter queues (DLQs) for failed dispatches.
- Strict at-least-once delivery guarantees for all notifications, and exactly-once processing for billing-critical events.
- A future-proof structure that supports real-time WebSocket push notifications within 2 quarters.
- Ability to scale to a 10x traffic target (up to 5,000 req/s at peak, ~20M tasks/month) without subsequent architectural rewrites.

### Team and Operational Constraints
- **Resource Constraints**: A lean engineering team of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure or DevOps engineer.
- **Experience Constraints**: The team has zero operational or development experience with Apache Kafka.
- **Timeline Constraints**: The solution must be implemented, tested, and delivering production value in under 2 weeks.
- **Financial Constraints**: Budget is modest; a high-tier fully managed solution like Confluent Cloud is financially unviable at our 10x scale target today.
- **Existing Tech Stack**: The infrastructure already runs Redis for session storage and rate limiting.

---

## Decision

We will use **Redis Streams** as the backbone message broker for our asynchronous notification subsystem, rejected Apache Kafka.

### Justification
Redis Streams offers an optimal balance of throughput, delivery guarantees, and operational simplicity. By leveraging our existing Redis infrastructure, we avoid the substantial time, budget, and operational risks of Apache Kafka, while fully meeting our performance and architectural requirements.

1. **Operational and Resource Alignment**:
   Our 6-person team cannot afford the overhead of operating self-hosted Kafka (ZooKeeper/KRaft, JVM tuning, broker state management, disk replication), nor does our budget permit fully managed Kafka. Since Redis is already running and monitored in our production environment, introducing Redis Streams has **zero operational cost, zero incremental licensing/cloud cost, and a near-zero learning curve**.
2. **Timeline Feasibility**:
   Implementing Redis Streams using standard Python clients (e.g., `redis-py`) can be completed, load-tested, and deployed within our strict 2-week limit. Building, configuring, and verifying a reliable Kafka broker setup and testing consumer group rebalancing would consume our entire development bandwidth, risking missed deadlines.
3. **Technical Capabilities at Scale**:
   Our 10x scaling peak of 5,000 req/s is well within the capabilities of a single-core Redis instance, which can comfortably process over 50,000 write/read operations per second. Redis Streams guarantees strict FIFO ordering of messages within each stream using auto-incrementing time-based IDs (e.g., `1000-0`), matching Kafka's partition-level ordering guarantees without the overhead of partitioning key design. It supports consumer groups natively via `XGROUP`, `XREADGROUP`, `XPENDING`, `XCLAIM`, and `XACK`, satisfying all asynchronous queue requirements.
4. **Achieving Exactly-Once Semantics for Billing**:
   True exactly-once end-to-end delivery for external side-effects (such as sending emails via SMTP or triggering external webhooks) is mathematically impossible via the broker alone, because a network partition can always fail *after* the external side-effect occurs but *before* the broker acknowledges receipt. Thus, exactly-once delivery must be achieved via an **Idempotent Consumer pattern** at the application layer. We will enforce this by persisting a unique `notification_id` and its processing state in our existing PostgreSQL database within a transaction. Since PostgreSQL is already our primary database, this implementation is trivial with Redis Streams and would have been required even with Kafka.

---

## Consequences

### Positive (Pros)
- **Zero New Infrastructure**: We do not need to provision, secure, configure, monitor, or pay for any new servers, stateful clustering, or VMs.
- **Immediate Path to WebSockets**: Redis's in-memory speed and pub/sub extensions make it a perfect companion for real-time WebSocket servers (e.g., Socket.IO or Gevent-WebSocket), which we can seamlessly integrate in the coming quarters.
- **Extremely Low Latency**: Message write (`XADD`) and read (`XREAD`) latencies are sub-millisecond, maximizing Flask thread availability.
- **Robust Error Handling**: Using Redis consumer groups, we can query `XPENDING` to detect dead workers, reclaim abandoned notifications using `XCLAIM`, and route poisoned messages to a dedicated stream representing a Dead Letter Queue (DLQ) after a fixed number of retries.
- **Decoupled Resiliency**: All notification execution is moved to separate consumer processes. Slow webhook endpoints and email timeouts will only consume worker capacity, preventing cascading failures and connection pool exhaustion in our web monolith.

### Negative (Cons)
- **In-Memory Risk**: By default, Redis is an in-memory database. A sudden crash could result in data loss if messages are not fully written to disk. 
  - *Mitigation*: We will enable Append-Only File (AOF) persistence with `fsync everysec` on our Redis instance. For high-value billing events, we will implement the **Transactional Outbox pattern**: billing notifications will be committed to a PostgreSQL table (`outbox`) inside the primary transaction and subsequently dispatched to Redis Streams by a reliable publisher process.
- **Memory Consumption Limits**: Unlike Kafka, which stores petabytes of events on disk, Redis Streams resides in RAM.
  - *Mitigation*: We will enforce message trimming using the approximate trimming operator (`MAXLEN ~ 10000`) on `XADD` to bound stream size, ensuring memory consumption remains low and predictable. Long-term history will be archived in PostgreSQL rather than kept in the Redis Stream.
- **Python Threading/Async Complexity**: Python's Flask is synchronous, so workers executing long-running network operations (emails, webhooks) must run as separate daemon processes (using packages like `gunicorn` with worker-class configuration or Celery with a Redis broker backend, or simple standalone consumer loops utilizing `redis-py`).

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka due to its extreme operational complexity, cost barriers, and mismatch with our resource constraints:
- **Operational Overhead**: Kafka is designed for high-volume log ingestion and analytics pipelines (gigabytes per second) across massive distributed teams. A 6-person team with no dedicated infrastructure engineer would be overwhelmed by configuring and managing a production-ready multi-node Kafka cluster (or ZooKeeper/KRaft), handling disk space, rebalancing partitions, and monitoring JVM garbage collection.
- **Setup Time & Cost**: Setting up Kafka, establishing its deployment pipelines, and integrating it with Python drivers would take 3–4 weeks minimum, missing our 2-week deadline. Offloading this to a managed provider like Confluent Cloud exceeds our budget.
- **Over-Engineering**: Our scaling target of 5,000 req/s represents lightweight throughput. Using a distributed commit log designed for high-throughput event sourcing to run ephemeral notification queues is highly inefficient.

*We would have chosen Apache Kafka if:*
1. Our scale exceeded 100,000 events per second.
2. We had a dedicated DevOps engineer or infrastructure specialist.
3. We had the budget to run a fully-managed Confluent Cloud cluster.
4. We required multi-month retention of raw events for analytical replay or stream joining.
