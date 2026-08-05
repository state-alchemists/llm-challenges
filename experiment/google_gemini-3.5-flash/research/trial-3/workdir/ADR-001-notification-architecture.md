# ADR-001-notification-architecture

## Title
ADR-001: Selection of Redis Streams over Apache Kafka for the Notification Subsystem

## Status
Proposed

## Context
We operate a SaaS project management platform experiencing significant growth, currently supporting 85,000 monthly active users (MAU) and processing approximately 2 million tasks per month. Peak traffic reaches roughly 500 requests per second (req/s) during business hours. 

The current system architecture consists of a 50,000-line Python/Flask monolith deployed across four AWS web servers behind an Nginx load balancer. The database layer utilizes a single primary PostgreSQL instance with one read replica. Redis is already running in production, used solely for session storage and rate limiting.

Currently, the notification module—responsible for dispatching emails and executing outbound webhooks when tasks are updated, assigned, or completed—operates synchronously within the HTTP request cycle. This design has introduced severe production vulnerabilities:
1. **Request Timeouts**: Dispatching notifications synchronously blocks HTTP responses, resulting in an average latency of 800ms, which regularly spikes to 8,000ms during peak business hours.
2. **Silent Failures**: If external email providers (e.g., SendGrid) or client webhook endpoints are offline, notifications are dropped without automated retries or Dead-Letter Queue (DLQ) containment.
3. **Cascading Failures**: Slow webhook target endpoints have twice exhausted the PostgreSQL connection pools, causing cascading failures that took down unrelated platform capabilities.
4. **Lack of Delivery Guarantees**: Critical billing-related notifications (e.g., "trial expired", "payment failed") have no delivery guarantees, despite requiring exactly-once semantics.

### Scaling and Feature Targets
To address these problems, the new notification subsystem must:
- Decouple notification logic from the synchronous HTTP request cycle.
- Support retry mechanisms with exponential backoff and jitter.
- Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- Support real-time WebSocket push notifications to browser clients within two quarters.
- Scale to support a 10x traffic growth target (5,000 req/s peak, ~20M tasks/month) without a complete architectural rewrite.

### Organizational and Technical Constraints
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure engineer**.
- **Setup Window**: The system must deliver production value within **2 weeks** of starting setup and migration.
- **Budget**: Modest budget; cannot support high recurring costs such as managed Kafka (e.g., Confluent Cloud) at our scaling target.
- **Existing Footprint**: Redis is already fully operational in production, and the team is comfortable monitoring it.
- **Technology Gap**: The team has **zero operational experience** with Apache Kafka.

---

## Decision
We choose **Redis Streams** as the underlying message broker for the notification subsystem, rejecting Apache Kafka.

### Justification
Redis Streams provides a low-overhead, high-performance messaging interface that leverages our existing production infrastructure. This eliminates the operational risks associated with learning, provisioning, and maintaining a new Kafka cluster for our 6-person team under a tight 2-week timeline. 

Redis Streams natively supports consumer groups (`XGROUP`), explicit processing acknowledgements (`XACK`), and consumer crash recovery via pending message claiming (`XCLAIM`). Combined with an application-level **Idempotent Consumer pattern** implemented in our Python monolith using PostgreSQL transactions, we can guarantee exactly-once processing for billing notifications at a fraction of the cost and complexity of Kafka.

---

## Consequences

### Pros (Benefits)
1. **Near-Zero Operational Complexity**: We are already running Redis in production. Introducing Redis Streams requires zero new infrastructure provisioning, no new security/network configurations, and no new monitoring stack. This fits our 6-person, infrastructure-engineer-less team perfectly.
2. **Immediate Time-to-Market (Under 2 Weeks)**: The APIs for Redis Streams are highly intuitive and accessible via our existing `redis-py` library. A functional prototype and production-ready async worker pool can be coded, tested, and shipped in days rather than weeks.
3. **High Throughput and Low Latency**: Operating in-memory, a single Redis node can handle >100,000 operations per second with sub-millisecond latencies. Scaling to our 10x peak target (5,000 req/s) is trivial and consumes negligible CPU and memory, eliminating any throughput concerns.
4. **Robust Consumer Groups**: Redis Streams tracks unacknowledged messages per consumer group in a Pending Entries List (PEL). If a worker process dies mid-execution, surviving workers can inspect the PEL and use `XCLAIM` to safely re-process stalled notifications, ensuring at-least-once delivery.
5. **Path to WebSockets**: Redis's low-latency performance and existing pub/sub features integrate seamlessly with WebSocket gateways (e.g., standard Python ASGI servers running Eventlet or Gevent). This simplifies our 2-quarter roadmap target of delivering real-time push notifications.
6. **Extremely Cost-Effective**: By using our existing Redis instance (scaling it vertically if necessary, or using standard Redis Replication), we avoid the high setup and monthly operational costs of managed Apache Kafka.

### Cons (Drawbacks and Mitigations)
1. **In-Memory Storage Cost**: Because Redis keeps its dataset in RAM, unbounded stream growth will lead to Out-Of-Memory (OOM) failures or eviction of active session data.
   - *Mitigation*: We will enforce capped streams during publication using the `MAXLEN` option (e.g., `XADD notification_stream MAXLEN ~ 50000 * ...`) to restrict RAM footprint.
2. **No Native Long-Term Message Retention**: Once a stream is trimmed or messages are acknowledged and deleted, they cannot be replayed from the broker.
   - *Mitigation*: We do not use the message broker as a database. We will record the terminal delivery state of all notifications (success, failure, logs) directly to PostgreSQL, which has a dedicated read replica. PostgreSQL will serve as our long-term, durable audit trail.
3. **No Native Exactly-Once Semantics (EOS)**: Unlike Kafka's transactional API, Redis Streams does not support native exactly-once guarantees.
   - *Mitigation*: We will implement an application-level **Idempotent Consumer pattern**. Each published notification message will carry a unique `message_id` (UUIDv4) in its payload. When a consumer picks up a billing notification, it executes the operation inside a PostgreSQL transaction that inserts the `message_id` into a `processed_notifications` table. If the database raises a unique constraint violation, the consumer skips processing, securing end-to-end exactly-once semantics.

---

## Alternatives Considered

### Apache Kafka
We evaluated Apache Kafka as the industry-standard event streaming platform, but rejected it based on the following evaluations:

- **High Operational Complexity**: Kafka requires significant management overhead, including partitions, replication factors, consumer group rebalancing, and ZooKeeper/KRaft cluster configuration. Without a dedicated infrastructure engineer, self-hosting Kafka introduces a substantial risk of misconfiguration, leading to message loss or service outages.
- **Budget and Timeline Misalignment**: Deploying, securing, and thoroughly testing a Kafka setup within our 2-week window is unrealistic for a team with no prior experience. Choosing managed services like AWS MSK or Confluent Cloud would alleviate operational tasks but violates our modest budget constraints.
- **Scale Overkill**: Kafka is optimized for ingestion of massive event streams (millions of events per second). Proposing Kafka for a peak of 5,000 req/s is severe over-engineering. Redis Streams offers more than enough headroom to scale past our 10x target.
- **The Exactly-Once Fallacy**: While Kafka natively supports exactly-once processing, this guarantee only applies to pipelines within Kafka (Kafka-to-Kafka). It cannot ensure exactly-once delivery when communicating with external, non-transactional HTTP systems, such as third-party email APIs (SendGrid) or arbitrary customer webhook endpoints. Because our workers must execute network calls outside of Kafka's boundary, we would still need to implement application-level deduplication and PostgreSQL idempotency checks. Consequently, Kafka's native exactly-once feature does not solve our primary exactly-once challenge, making its high complexity unjustifiable.
