# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform currently services 85,000 monthly active users, processing approximately 2 million task creations per month with a peak throughput of ~500 requests per second (req/s) during business hours. 

The notification system (responsible for dispatching emails and webhooks when tasks are updated, assigned, or completed) is currently coupled synchronously to the HTTP request cycle of our Python/Flask monolith. This design has introduced severe operational and reliability issues:
1. **Request Timeouts**: Sending notifications blocks the client response. Average request latency has degraded to 800ms, with spikes up to 8s during peak hours.
2. **Silent Failures**: The absence of retries or a Dead-Letter Queue (DLQ) causes notifications to be silently dropped whenever third-party email providers or webhook endpoints experience downtime.
3. **Cascading Failures**: Slow webhook targets have repeatedly exhausted our database connection pools, leading to platform-wide outages affecting unrelated features.
4. **No Delivery Guarantees**: Critical billing notifications (e.g., "trial expired", "payment failed") are treated the same as transactional task notifications and lack delivery guarantees.

### Scaling and Architectural Targets
To resolve these issues and prepare for a projected 10x traffic growth (reaching peak volumes of ~5,000 req/s), we must meet the following objectives:
- **Asynchronous Decoupling**: Offload notifications from the HTTP request cycle.
- **Reliable Retries**: Implement exponential backoff with a Dead-Letter Queue.
- **Delivery Guarantees**: Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- **Real-Time Integration**: Support real-time WebSocket push notifications within 2 quarters.
- **Future-Proofing**: Handle the 10x traffic scaling (~5,000 req/s) without a complete system re-architecture.

### Operational and Business Constraints
- **Team Size**: Only 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure or DevOps engineer.
- **Technical Expertise**: Zero prior experience with Apache Kafka on the team.
- **Existing Infrastructure**: We already deploy and operate Redis in production for session storage and rate limiting.
- **Time-to-Value**: The migration and setup phase must not exceed 2 weeks before we start delivering value.
- **Budget**: Modest budget; managed enterprise Kafka solutions (such as Confluent Cloud) are cost-prohibitive at our target scale.

---

## Decision
We will use **Redis Streams** as the underlying message broker for the notification subsystem. 

### Justification

1. **Operational Simplicity & Team Velocity**:
   Introducing Apache Kafka would require substantial time and expertise to configure, secure, and monitor. With a 6-person team and no dedicated DevOps engineer, self-hosting a high-availability Kafka cluster (utilizing ZooKeeper or KRaft) is a high-risk operational liability. Conversely, Redis is already operational in our production stack. Leveraging Redis Streams introduces zero new infrastructure dependencies, allowing the team to deliver value well within the 2-week constraint.

2. **Throughput Compatibility**:
   While Kafka is built for massive ingestion rates (millions of events/sec), our 10x peak projection of ~5,000 req/s is well within the capabilities of a single-node Redis instance. Redis Streams handles tens of thousands of write/read operations per second with sub-millisecond in-memory latencies, satisfying our scaling targets without infrastructure bloat.

3. **Built-in Consumer Groups**:
   Redis Streams provides robust, native consumer group support (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`). This allows multiple Python worker processes to consume messages concurrently, distributing load and supporting reliable horizontal scaling of our consumer tier.

4. **Guaranteed At-Least-Once Delivery**:
   Redis Streams tracks unacknowledged messages per consumer using a Pending Entries List (PEL). If a worker crashes mid-execution, unacknowledged notifications can be claimed by another worker via `XPENDING` and `XCLAIM`, eliminating silent drops and ensuring at-least-once delivery for billing-critical events.

5. **Strict Ordering Guarantees**:
   Redis Streams natively maintains strict chronological message ordering within each stream using auto-incrementing, time-based entry IDs. Consumers read events in the exact sequence they occurred. While Kafka also guarantees ordering, it does so only within a single partition. Managing order in Kafka across multiple partitions requires complex partitioning keys (e.g., hash of task ID or user ID) or restricting a topic to one partition, which creates bottlenecks. Redis Streams provides simple, out-of-the-box FIFO ordering for task updates.

6. **Exactly-Once Semantics (EOS) Realities**:
   Achieving true exactly-once delivery in a notification system requires application-layer idempotency. Since we are dispatching side effects to third-party endpoints (email APIs, external webhooks), network failures can occur after an email is sent but before the broker receives an acknowledgment. Neither Kafka's native EOS nor Redis Streams can solve this externally. 
   
   To achieve exactly-once processing for billing, we will implement application-layer deduplication. We can use Redis's high-speed in-memory store to track unique event IDs (acting as a distributed deduplication lock) alongside PostgreSQL unique constraints. Using Redis Streams makes this distributed state check extremely fast and colocated.

7. **WebSocket Synergy**:
   Our roadmap requires real-time WebSocket push notifications within 2 quarters. Having our message broker (Redis Streams) run on the same Redis engine already used for session management simplifies the design of a highly scalable WebSocket backend (e.g., using Redis Pub/Sub or Streams to coordinate messages across multiple stateless WebSocket servers).

---

## Consequences

### Positive (Pros)
- **Zero Additional Infrastructure Overhead**: No new clusters to provision, patch, monitor, or manage. We use our existing Redis deployment.
- **Sub-Millisecond Latency**: In-memory message processing guarantees exceptionally fast queue-append and fetch times.
- **Immediate Developer Onboarding**: The team is already familiar with Redis. Writing to and reading from Redis Streams via standard Python libraries (e.g., `redis-py`) is straightforward and fast to implement.
- **Efficient Resource Utilization**: Fits easily within our current infrastructure budget and requires minimal AWS operational spend.
- **At-Least-Once Reliability**: Built-in consumer group acknowledgments, PEL tracking, and message claiming ensure no notifications are lost during worker crashes.

### Negative (Cons)
- **Memory Bounds**: Redis is entirely in-memory. Unbounded streams will eventually exhaust RAM and crash the instance. 
  * *Mitigation*: We must enforce stream capping on every write using `XADD` with the `MAXLEN ~` parameter (e.g., keeping only the last 100,000 messages) and establish a background archiving process to push old notification logs to PostgreSQL or cold storage if long-term audit trails are needed.
- **Durability Risks**: Unlike Kafka's disk-first write-ahead log, Redis durability depends on our persistence configuration (RDB snapshots and AOF). A hard crash could result in data loss if AOF is not configured with `appendfsync everysec` or `always`.
  * *Mitigation*: We will configure our Redis instance with Append-Only File (AOF) enabled (`appendfsync everysec`). For critical billing notifications, we will write the notification state to our highly durable PostgreSQL primary database in the same transaction that creates the billing event, and use Redis Streams strictly as a transient trigger mechanism.
- **Lack of Native Replaying**: Redis Streams supports reading from arbitrary IDs, but because we must cap the stream length to save memory, we cannot replay weeks of historical data.
  * *Mitigation*: Long-term message retention is out of scope for transient notifications. PostgreSQL remains our source of truth for transactional histories.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:

- **Prohibitive Operational Complexity**: Kafka requires an experienced system administrator to manage partition offsets, broker replication, cluster balancing, and ZooKeeper/KRaft state. Without a dedicated infrastructure engineer, our 6-person team would spend disproportionate effort maintaining the broker rather than developing core product features.
- **Incompatible Time and Budget Constraints**: Setting up, testing, and securing a production-grade, highly available Kafka cluster would exceed our 2-week timeline. Utilizing Confluent Cloud is blocked by our modest budget constraints.
- **Over-engineered for Scale**: Kafka’s massive horizontal scaling capabilities are designed for high-throughput log ingestion. Our peak target of ~5,000 req/s represents an underutilization of Kafka's architecture, making the operational tax unjustifiable.
- **No Out-of-the-Box Exactly-Once for External Systems**: While Kafka features transactional producers and consumers, this capability is restricted to data flowing strictly *within* Kafka itself (e.g., reading from one topic and writing to another). Because our notification system must call external email providers (SendGrid/Mailgun) and customer webhooks, Kafka cannot prevent duplicate delivery if the external call succeeds but the Kafka offset commit fails. Application-layer deduplication is mandatory regardless of the broker; therefore, Kafka’s native transactional feature provides no comparative advantage for our specific use case.
