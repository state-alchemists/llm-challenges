# Title: ADR-001 - Notification Subsystem Architecture: Redis Streams vs. Apache Kafka

## Status
Proposed

## Context
Our SaaS project management platform is experiencing severe performance and reliability issues in the notifications module. This module is responsible for sending emails and triggering webhooks when tasks are updated, assigned, or completed. 

### Current Metrics and Architecture
- **Metrics**: 85,000 monthly active users (MAU), ~2M tasks created per month, and peak traffic reaching ~500 requests/second (req/s) during business hours.
- **Backend Stack**: Python/Flask monolith (~50k lines of code) running on 4 web servers behind an Nginx load balancer on AWS.
- **Database**: PostgreSQL (single primary, one read replica).
- **Cache**: Redis, currently utilized only for session storage and rate limiting.
- **Notification Flow**: Handled synchronously inside the HTTP request cycle.

### The Problem
As our usage has scaled, synchronous notification handling has introduced severe bottlenecks:
1. **Request Timeouts**: Sending notifications synchronously blocks responses. The average request latency is 800ms, frequently spiking to 8s during peak hours, causing HTTP timeouts.
2. **Silent Failures**: If an email provider or webhook endpoint is down, the notification is silently dropped. There is no retry mechanism or Dead-Letter Queue (DLQ).
3. **Cascading Failures**: Unreliable or slow downstream webhook endpoints have twice caused PostgreSQL connection pool exhaustion, leading to full-system outages affecting unrelated features.
4. **No Delivery Guarantees**: Billing-critical notifications (e.g., "trial expired," "payment failed") must have guaranteed delivery, but the current system provides none.

### Scaling Targets and Constraints
To address these issues and handle a projected **10x traffic growth** (~5,000 req/s peak, ~20M tasks/month) without re-architecting, we must satisfy the following constraints:
- **Decoupled Processing**: Decouple notifications from the HTTP request cycle via asynchronous processing.
- **Robust Retries**: Support retries with exponential backoff and a dead-letter queue.
- **Delivery Guarantees**: Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- **Real-Time Push**: Add real-time WebSocket push notifications within 2 quarters.
- **Timeframe**: Deliver value within a strict **2-week setup/migration window**.
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure engineer**.
- **Experience**: Zero prior Apache Kafka experience on the team.
- **Budget**: Modest; we cannot afford managed Apache Kafka (e.g., Confluent Cloud) at full scale today.
- **Existing Tech Stack**: We already run and monitor Redis in production for sessions and rate limiting.

---

## Decision
We will use **Redis Streams** as the core message broker for the decoupled notification subsystem. 

### Justification
Redis Streams provides the ideal set of technical capabilities (throughput, consumer groups, ordering guarantees) while perfectly matching our operational constraints (existing infrastructure, 6-person team, 2-week deadline, modest budget).

1. **Throughput and Latency**:
   Redis operates entirely in-memory, delivering sub-millisecond read/write latencies. A single Redis instance can easily handle >50,000 commands/sec. Our 10x peak target of 5,000 req/s represents only a fraction of Redis's capability, ensuring we can scale without re-architecting and with minimal resource utilization.
   
2. **Operational Simplicity**:
   Because we already run and monitor Redis in production, adopting Redis Streams introduces zero new infrastructure overhead. No new virtual machines, clustering software, or external monitoring agents are required. The engineering team can start writing and testing code immediately, easily meeting the 2-week time-to-value constraint.

3. **Robust Consumer Groups (`XGROUP`, `XREADGROUP`)**:
   Redis Streams provides first-class support for consumer groups. It tracks which message is read by which consumer and maintains a **Pending Entries List (PEL)**. If a worker process crashes mid-execution, other workers can query the PEL, claim the message using `XCLAIM`, and safely retry it. This is exactly the capability required to implement robust retries, exponential backoffs, and dead-letter queues.

4. **Exactly-Once Semantics (EOS)**:
   Our system requires exactly-once processing for critical billing notifications. Since external systems (e.g., SendGrid for emails, third-party webhook endpoints) do not participate in distributed database transactions, a message broker's internal exactly-once transactional API (like Kafka's) cannot prevent duplicate delivery if a network partition occurs *after* the external call is made but *before* the broker transaction commits.
   
   To solve this, we will implement an **Idempotent Consumer pattern** at the application level. When a billing event is published, we will attach a unique event UUID. The consumer will insert this UUID into a PostgreSQL `processed_notifications` table within the same database transaction that updates the billing/task state. If the UUID already exists, the transaction fails and the message is safely discarded. This standard, robust approach achieves exactly-once semantics and functions identically regardless of whether the underlying broker is Redis Streams or Kafka.

5. **Future-Proofing for WebSockets**:
   Using Redis Streams and Redis Pub/Sub aligns perfectly with our 2-quarter target for real-time WebSocket push notifications. Python WebSocket servers (such as Flask-SocketIO or custom asyncio/gevent services) integrate natively and efficiently with Redis's event-driven pub/sub architecture.

---

## Consequences

### Pros (Benefits)
* **Immediate Deployment**: No infrastructure setup required. The team can deploy the new architecture to production on day one using the existing Redis cluster.
* **Minimal Operational Burden**: With no dedicated infrastructure engineer, keeping our tech stack simple prevents operational fatigue and allows the team to focus on building features rather than managing brokers.
* **Sub-Millisecond Performance**: Message publishing and consumption are in-memory, drastically reducing queue latencies compared to disk-bound brokers.
* **Low Hosting Cost**: Zero additional software or cloud management fees. We can scale our existing Redis node or provision a small, cheap dedicated Redis replica if isolation is needed.
* **Message Delivery Guarantees**: Using the PEL and explicit acknowledgements (`XACK`), we guarantee at-least-once delivery for all notification events.

### Cons (Drawbacks and Trade-offs)
* **Memory Limits (In-Memory Storage)**: Redis Streams stores all messages in memory, meaning unbounded queue growth could cause Out-Of-Memory (OOM) crashes.
  * *Mitigation*: We must strictly bound stream sizes. We will append messages using the `MAXLEN ~ 10000` option with `XADD` (or run periodic `XTRIM` jobs) to cap memory usage. Processed notifications that require long-term audit trails will be archived to a lightweight, disk-backed PostgreSQL audit table.
* **Lack of Historical Replayability**: Unlike disk-backed brokers, once a message is acknowledged and trimmed in Redis, it cannot be easily replayed from the broker.
  * *Mitigation*: Since notifications are ephemeral events, historical replay from the broker is not a core requirement. If we need to re-send historical notifications, we can rebuild the payload from PostgreSQL records.
* **Durability Trade-off**: Redis persistence (AOF with `appendfsync everysec`) guarantees durability with the small trade-off of losing up to 1 second of data in a catastrophic hardware failure.
  * *Mitigation*: For standard email and webhook notifications, this minor risk is highly acceptable. For business-critical billing events, we will dual-write the event record to PostgreSQL before publishing to Redis Streams, providing a fallback source of truth.

---

## Alternatives Considered

### Apache Kafka (Rejected)
While Apache Kafka is a powerful and highly resilient distributed streaming platform, we rejected it for the following reasons:

1. **Extreme Operational Complexity**: Kafka is famously difficult to deploy, configure, and operate. Managing brokers, partition offsets, replication factors, and either ZooKeeper or KRaft metadata requires deep expertise. Without a dedicated infrastructure engineer, our 6-person team would be overwhelmed by cluster maintenance, JVM tuning, and disk-capacity management.
2. **Violation of Time Constraints**: The team has zero Kafka experience. Setting up a production-ready, highly available Kafka cluster, configuring monitoring/alerting, and learning the ecosystem inside Python within a 2-week window is impossible.
3. **Prohibitive Financial Costs**: Managed Kafka services (such as Confluent Cloud or AWS MSK) are extremely expensive at scale and would quickly exhaust our modest budget. Self-hosting on EC2 is also costly in both compute resources and engineering maintenance hours.
4. **Overkill for Our Scale**: Kafka is designed for ingestion rates of hundreds of thousands of events per second. Our 10x scaling target of 5,000 req/s is easily handled by a single Redis node. Adopting Kafka would represent a severe case of over-engineering.
5. **No Advantage for Exactly-Once Semantics (EOS) with External APIs**: Kafka's transactional EOS is highly effective within the Kafka-Streams ecosystem. However, because our notification subsystem must integrate with external email and webhook HTTP APIs, Kafka cannot enforce end-to-end exactly-once without application-level deduplication. Thus, Kafka offers no consistency advantage over Redis Streams for this specific use case.
