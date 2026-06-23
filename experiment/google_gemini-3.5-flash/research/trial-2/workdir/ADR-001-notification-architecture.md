# ADR 001: Notification Subsystem Architecture Decision Record

## Title
ADR-001: Adopting Redis Streams for the Async Notification Subsystem

## Status
Accepted

## Context

### Problem Statement
Our SaaS project management platform is experiencing severe degradation of the notification module (emails and webhooks). Currently, notifications are handled synchronously within the HTTP request cycle of our Python/Flask monolith. This has led to:
1. **Request Timeouts:** Synchronous processing blocks the client response. Average latency has reached 800ms, spiking to 8 seconds during peak hours.
2. **Silent Failures:** External dependency failures (e.g., email provider down, slow webhook endpoints) result in permanently dropped notifications. We have no retry mechanisms, dead-letter queues (DLQs), or delivery tracing.
3. **Cascading Failures:** External webhook latencies have twice caused backend connection pool exhaustion, leading to full system outages for unrelated features.
4. **No Delivery Guarantees:** Critical billing notifications (e.g., "trial expired", "payment failed") are sent without at-least-once or exactly-once delivery guarantees.

### Scaling & Operational Targets
- **Throughput Scale:** Transition from current peak (~500 req/s and ~2M tasks/month) to a 10x target (~5,000 req/s and ~20M tasks/month) without major re-architecting.
- **Time-to-Market:** The solution must be production-ready and delivering value within **2 weeks**.
- **WebSockets:** Implement real-time WebSocket push notifications within 2 quarters.
- **Budget & Team Size:** We have a modest budget (managed enterprise solutions like Confluent Cloud are cost-prohibitive). The engineering team consists of only 6 people (3 senior, 3 mid-level), with **no dedicated infrastructure or platform engineer**.
- **Existing Infrastructure:** We currently run a Python/Flask monolith, a PostgreSQL database (primary + read replica), and Redis (used for session storage and rate limiting).

---

## Decision

We will adopt **Redis Streams** as the underlying message broker and event streaming engine for our decoupled, asynchronous notification subsystem. 

We explicitly reject the adoption of **Apache Kafka** due to its prohibitive operational complexity, high learning curve, budget misalignment, and failure to meet our 2-week time-to-market constraint.

### Technical Justification

#### 1. Low Operational Complexity & Low Cost
Our primary constraint is our team size (6 engineers) and the lack of a dedicated infrastructure engineer.
- **Redis Streams:** We already run Redis in production for session storage and rate limiting. There is existing operational familiarity, backup processes, and monitoring in place. Adopting Redis Streams introduces zero new infrastructure dependencies, zero setup cost, and negligible operational overhead.
- **Apache Kafka:** Running self-hosted Kafka (either via ZooKeeper or KRaft) is highly complex, requiring specialized knowledge in JVM tuning, disk write patterns, partition replication factor, cluster consensus, and networking. Managed solutions like Confluent Cloud are excluded due to our modest budget. Adding Kafka would consume the majority of our engineering capacity just for maintenance.

#### 2. Throughput & Scaling Profile
- **Current & 10x Scale:** 20M tasks/month equates to an average of ~8 tasks per second. Even at a peak rate of 5,000 req/s generating up to 5,000 notifications per second, Redis is more than capable.
- **Performance:** Redis is an in-memory data store capable of handling over 100,000 write operations per second on a single, modest virtual machine. Redis Streams easily scales far beyond our 10x target with sub-millisecond latencies, whereas Kafka's massive horizontal scaling capabilities are highly over-engineered for our requirements.

#### 3. Message Retention & Memory Management
- **Mechanism:** Redis Streams stores all active streams in-memory (RAM). Left unchecked, this would result in memory exhaustion.
- **Retention Strategy:** We will utilize capped streams using the `MAXLEN` or `MINID` arguments during appending (`XADD`) or periodic trimming (`XTRIM`). We will maintain a rolling window of the last 7 days of raw notification events (approximately 5M messages under peak 10x load, consuming < 2GB of RAM).
- **Archival & Auditing:** For long-term historical audits, successfully processed or dead-letter notifications will be written asynchronously to our primary PostgreSQL database, which handles persistent disk storage.

#### 4. Delivery Guarantees & Exactly-Once Semantics (EOS)
Our billing notifications require extremely strict delivery guarantees.
- **At-Least-Once Delivery via Redis Consumer Groups:** Redis Streams natively supports consumer groups (`XGROUP`). Consumers will read messages using `XREADGROUP`, track pending deliveries in the Pending Entries List (PEL) via `XPENDING`, and acknowledge them via `XACK`. If a consumer worker crashes before acknowledging, other workers can claim the orphaned message using `XCLAIM` after a visibility timeout, ensuring at-least-once delivery.
- **Exactly-Once Processing (EOP) Technical Reality:** True exactly-once delivery across external network boundaries (such as executing an HTTP POST to a customer's webhook or calling the SendGrid API) is a mathematical impossibility due to the Two Generals' Problem. If an email is successfully sent but the provider's API acknowledgment is lost in transit, retries will cause duplicates.
- **Application-Layer Idempotency:** To achieve *effectively exactly-once* execution, we must design our consumers to be idempotent. We will generate a unique deterministic idempotency key for each billing notification (e.g., `UUIDv5(event_type + billing_event_id)`). The Python/Flask consumer will execute the notification delivery inside a database transaction, logging the processed idempotency key using a PostgreSQL `UNIQUE` constraint (`INSERT ... ON CONFLICT DO NOTHING`).
- **Kafka's EOS Limitation:** Kafka's transactional API only guarantees exactly-once delivery internally within the Kafka ecosystem (from one topic to another). It does not solve the external API delivery problem, meaning we would still have to implement application-layer idempotency. Thus, Kafka offers no technical advantage for our specific billing notifications while adding massive complexity.

#### 5. Ordering Guarantees
- **Redis Streams:** Within a stream, Redis assigns sequential IDs (`<timestamp>-<sequence>`) and strictly guarantees FIFO (First-In, First-Out) ordering. Because we are processing notifications asynchronously, serial execution per user/task can be strictly preserved by routing messages sequentially or mapping them to deterministic consumer routing.

#### 6. Real-time WebSockets Integration
- **Unified Stack:** In 2 quarters, we must introduce real-time WebSocket push notifications. Redis is already the standard backbone for scaling WebSockets because of its extremely fast, low-overhead Pub/Sub engine. Relying on Redis for both the async job queue (Streams) and the WebSocket push channel (Pub/Sub) allows us to share the same unified in-memory infrastructure, drastically simplifying our system topology.

---

## Consequences

### Pros (Benefits of Redis Streams)
- **Time-to-Value:** Minimal setup. Integrating Redis Streams using `redis-py` in our Flask monolith takes less than 3 days of development, easily beating the 2-week deadline.
- **Zero Additional Cost:** No new infrastructure resources or expensive enterprise licenses are required.
- **Sub-millisecond Latencies:** In-memory queueing eliminates message broker latency.
- **Integrated Tooling:** Combines event streaming, pub/sub for WebSockets, session management, and rate limiting in a single operational dependency.
- **Robust Disaster Recovery:** Leverages existing Redis persistence settings (RDB and AOF sync `everysec`) and replication replicas to prevent data loss.

### Cons (Trade-offs & Mitigations)
- **In-Memory Limitations:** Unlike Kafka, which writes directly to disk, Redis stores streams in RAM.
  * *Mitigation:* We will strictly enforce capped stream lengths (`MAXLEN ~ 100,000` per stream type) and offload archival notification data to our PostgreSQL database.
- **No Native Schema Registry:** Redis Streams does not enforce payload schemas, which can lead to deserialization errors during updates.
  * *Mitigation:* Because our backend is a single Flask monolith (~50k LOC), we will enforce schema structure using Pydantic models at the application level before writing to the stream.
- **Broker-side Backpressure Lack:** Redis does not automatically slow down publishers if consumers are bottlenecked.
  * *Mitigation:* We will monitor queue lengths via Prometheus alerts on `XLEN`. If queue lengths exceed thresholds, we will scale up consumer instances (workers) dynamically.

---

## Alternatives Considered

### Apache Kafka
We thoroughly evaluated Apache Kafka as an alternative but rejected it for the following reasons:
1. **Severe Operational Complexity:** Setting up and managing a high-availability Kafka cluster is a full-time job. With a team of only 6 engineers and no dedicated infrastructure engineer, self-hosting is an unacceptable operational risk that would distract from core product features.
2. **Setup Timeline:** Designing topic partitions, configuring consumer poll intervals, handling complex cluster rebalancing bugs, and setting up network security on AWS would take at least 3-4 weeks, violating our 2-week delivery target.
3. **Budget Overrun:** Running self-hosted multi-node Kafka clusters on AWS requires substantial CPU and EBS provisioned IOPS. Managed Kafka (such as Confluent Cloud) is too expensive for our modest SaaS budget.
4. **Overkill for Scale:** Kafka is designed to process gigabytes of data per second and billions of events. Our 10x target is well within the capabilities of a single-instance Redis deployment, rendering Kafka’s horizontal scaling architecture unnecessary.
5. **No Advantage in External Exactly-Once:** Since our notifications are bound to external networks (emails/webhooks), Kafka’s internal transactional exactly-once guarantees do not help us bypass the need for application-level idempotency.
