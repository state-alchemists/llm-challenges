# ADR-001: Notification Subsystem Message Broker Selection

## Status
Accepted

## Context
Our SaaS project management platform currently processes 85,000 monthly active users (MAU), ~2M tasks per month, and experiences a peak load of ~500 requests/second during business hours (source: `system_context.md:4-6`). 

The current system handles notifications (emails and webhooks for task updates, assignments, and completions) synchronously inside the HTTP request cycle of our Python/Flask monolith (source: `system_context.md:9-14`). This architectural pattern has caused several critical production issues (source: `system_context.md:18-27`):
1. **Request timeouts**: Latency averages 800ms and spikes to 8s during peak hours because sending notifications blocks the client HTTP response.
2. **Silent failures**: Failed webhooks or email deliveries are silently dropped with no retries or dead-letter queue (DLQ) mechanisms.
3. **Cascading failures**: Webhook delivery bottlenecks have repeatedly exhausted the application's connection pools, leading to cascading failures that brought down unrelated monolith services.
4. **No delivery guarantees**: Critical billing-related notifications (e.g., payment failures, trial expirations) lack delivery guarantees.

To address these pain points, we must transition to an asynchronous notification subsystem. Our scaling targets and constraints are as follows:
- **Scaling Targets**: Handle a 10x traffic growth (reaching peak ~5,000 req/s, source: `system_context.md:34`) without requiring re-architecture. Assuming an average of 2–3 notifications are triggered per event, the system must process up to 15,000 notifications/s at peak. We also need to implement retry-with-exponential-backoff, guarantee at-least-once delivery (exactly-once processing where feasible for billing, source: `system_context.md:32, 43`), and support real-time WebSocket push notifications within 2 quarters (source: `system_context.md:33`).
- **Resource Constraints**: We have a small engineering team of 6 people (3 senior, 3 mid-level) and no dedicated infrastructure engineer (source: `system_context.md:37-38`). The team has zero Kafka experience (source: `system_context.md:40`).
- **Time Constraints**: The solution must be fully configured and delivering value within a strict 2-week window (source: `system_context.md:40`).
- **Budget Constraints**: We have a modest budget and cannot afford a high-cost managed Kafka service like Confluent Cloud at full scale (source: `system_context.md:41-42`).
- **Existing Tech Stack**: We already run a PostgreSQL database (single primary, one read replica) and a Redis instance used for session storage and rate limiting (source: `system_context.md:10-12, 39`).

We must evaluate two architectural options for the message broker backing this notification subsystem: **Apache Kafka** and **Redis Streams**.

---

## Decision
We choose **Redis Streams** as the message broker for our notification subsystem. 

### Justification

#### 1. Operational Simplicity and Team Constraints
Our small 6-person engineering team has no dedicated infrastructure engineer and zero Kafka experience (source: `system_context.md:37-38, 40`). Operating Apache Kafka in production (managing ZooKeeper/KRaft, partition limits, replication factors, JVM garbage collection, and disk capacity) represents a massive operational overhead that we cannot support. Redis is already running in our production stack (source: `system_context.md:12, 39`). Leveraging Redis Streams requires zero new infrastructure setup, utilizes the team's existing monitoring and scaling skills, and easily fits within our 2-week setup and migration deadline (source: `system_context.md:40`).

#### 2. Throughput Capabilities
Our 10x peak scaling target is ~5,000 requests/s (source: `system_context.md:34`), translating to approximately 10,000 to 15,000 notifications/s. Redis Streams operates entirely in-memory, allowing a single standard AWS ElastiCache Redis node to comfortably handle 100,000+ read/write operations per second. Redis Streams easily satisfies our 10x throughput requirements without complex partitioning.

#### 3. Real-Time WebSockets Integration
We must build real-time WebSocket push notifications within two quarters (source: `system_context.md:33`). Redis's sub-millisecond in-memory response times and seamless integration with pub/sub models make it exceptionally well-suited for pushing real-time events to active WebSocket connections. Kafka's pull-based architecture and consumer poll latencies introduce higher overhead and latency for real-time user-facing features.

#### 4. Practical Exactly-Once Semantics (EOS)
The system requires exactly-once semantics for critical billing notifications (source: `system_context.md:32, 43`). 
In distributed systems, true "exactly-once delivery" over a network to third-party endpoints (such as email APIs or external customer webhooks) is physically impossible due to the Two Generals' Problem. If an email service successfully sends an email but the network disconnects before returning an HTTP 200, the sender must retry, causing a duplicate.

Therefore, "exactly-once" must be achieved through **at-least-once delivery + consumer-side idempotency**:
- **At-Least-Once Delivery**: Redis Streams natively supports consumer groups with explicit message acknowledgment (`XACK`), pending list tracking (`XPENDING`), and consumer crash recovery (`XCLAIM`). This guarantees that no message is lost if a notification worker crashes mid-execution.
- **Idempotency**: We will generate a deterministic, unique UUID for every event (e.g., `event_id` or `notification_id`) at the producer side inside our Flask monolith. The notification worker will write this ID to our PostgreSQL database inside a unique-constrained table (`processed_notifications`) within the same transaction that updates our billing state. Alternatively, we can use Redis distributed locks (`SET NX`) for quick deduplication. If a duplicate notification is picked up, the worker will detect the existing key/record and return early without duplicate delivery.

#### 5. Budget Constraints
Self-hosting Kafka on EC2 would require significant engineering hours to configure securely, while managed solutions like Confluent Cloud are too expensive for our modest budget (source: `system_context.md:41-42`). Redis Streams runs on our existing Redis setup or a low-cost, fully-managed AWS ElastiCache instance, aligning perfectly with our financial constraints.

---

## Consequences

### Pros (Benefits)
- **Zero Infrastructure Overhead**: No new clusters to provision, patch, or configure. We build upon our existing, stable production Redis footprint (source: `system_context.md:12, 39`).
- **Immediate Time-to-Value**: Simple client integration via standard libraries (e.g., `redis-py`). This guarantees we can design, build, test, and ship the asynchronous notifier within the 2-week deadline (source: `system_context.md:40`).
- **High Performance and Low Latency**: In-memory speeds ensure notification dispatch takes microseconds from the application's perspective, decoupling the synchronous HTTP cycle and resolving our 800ms-8s latency bottleneck (source: `system_context.md:19-20`).
- **Excellent WebSocket Compatibility**: Seamlessly feeds into our upcoming WebSocket server architecture, keeping the technical stack clean and unified.
- **Robust Worker Failover**: Redis Streams' consumer group commands (`XPENDING`, `XCLAIM`) ensure that if a notification worker dies while sending an email or webhook, another worker can safely claim and retry the task.

### Cons (Drawbacks and Mitigations)
- **Memory-Bound Storage**: Because Redis is an in-memory store, storing notification history indefinitely will lead to memory exhaustion (OOM).
  * *Mitigation*: We will use the proactive trimming feature of Redis Streams (e.g., calling `XADD` with `MAXLEN ~ 100000` or using `XTRIM` periodically) to maintain a bounded rolling buffer of recent events. Historical audit logs of notifications will be written asynchronously to PostgreSQL, which acts as our long-term, durable persistent store (source: `system_context.md:10`).
- **Data Durability Concerns**: In default configurations, Redis can lose a small window of in-memory data during an unexpected node crash.
  * *Mitigation*: We will enable Append Only File (AOF) persistence on our Redis instance with `appendfsync everysec`. In the rare event of a master node crash, data loss is capped at a maximum of 1 second of messages. Since notifications (task updates, comments) are non-transactional and can be safely retried, this 1-second risk window is highly acceptable. Crucial billing-related state remains durably stored in PostgreSQL.
- **Lack of Built-In Retry and Backoff**: Redis Streams does not feature built-in exponential backoff retries or dead-letter queues.
  * *Mitigation*: We will implement a lightweight application-level retry loop. Failed notification jobs (e.g., due to third-party email provider downtime) will be caught by the worker, serialized, and pushed into a dedicated "retry stream" with a delay timestamp, or offloaded to PostgreSQL for scheduled retry sweeps. If a job fails repeatedly (e.g., 5 times), it will be moved to a PostgreSQL `dead_letter_notifications` table for manual administrative review.

---

## Alternatives Considered

### Apache Kafka (Rejected)
We thoroughly evaluated Apache Kafka as the backbone for the notification subsystem but rejected it due to the following reasons:

1. **Extreme Operational Overhead**: Self-hosting a production-grade, highly available Kafka cluster requires substantial expertise. The 6-person team has zero Kafka experience and no dedicated infrastructure engineer (source: `system_context.md:37-38, 40`). Selecting Kafka would force the team to pivot from product development to database administration, creating massive risk.
2. **Setup and Timeline Violation**: Installing, securing, configuring, and writing clients for Kafka in a highly reliable manner would take several weeks, heavily violating our 2-week delivery constraint (source: `system_context.md:40`).
3. **Budget Incompatibility**: Managed Confluent Cloud is financially unviable for our modest budget at our scaling targets (source: `system_context.md:41-42`).
4. **Vast Over-Engineering**: While Kafka can process millions of events per second, our peak 10x traffic requirement is 15,000 events/s (source: `system_context.md:34`). Redis Streams easily handles this throughput without the massive storage, disk, memory, and network overhead of Kafka.
5. **Misaligned Exactly-Once Capabilities**: While Kafka offers native transactional APIs that guarantee exactly-once processing internally (from Kafka topic A to Kafka topic B), this does not extend to outbound side-effects like sending emails or webhooks over HTTP. Because external APIs do not participate in Kafka transactions, the application must still implement consumer-side idempotency in PostgreSQL regardless of the broker chosen. Thus, Kafka's complex transactional capabilities provide no actual benefit for our core problem.
