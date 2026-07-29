# ADR-001: Notification Subsystem Architecture

## Status
Accepted

## Context
We run a SaaS project management platform with 85,000 monthly active users (MAU), generating ~2 million tasks per month. Our system experiences business-hour peak traffic of approximately 500 requests per second (req/s). 

### Current Architecture
* **Backend:** Monolithic Python/Flask application (~50k LOC) running on 4 web servers behind an Nginx load balancer on AWS.
* **Database:** PostgreSQL (single primary, one read replica).
* **Caching/NoSQL:** Redis, currently used for session storage and rate limiting.
* **Notification Dispatch:** Synchronous execution of emails and webhooks directly within the HTTP request/response cycle.

### Core Problems
1. **Request Timeouts:** Synchronous notification dispatch blocks HTTP worker threads, leading to an average response latency of 800ms, with peak spikes reaching up to 8 seconds.
2. **Silent Failures:** External email provider or webhook client failures cause notifications to be silently dropped, as there are no retry mechanism, acknowledgment tracking, or Dead-Letter Queues (DLQs).
3. **Cascading Failures:** Slow or unresponsive third-party webhook endpoints have exhausted Flask database connection pools twice this year, causing major outages in unrelated system modules.
4. **No Delivery Guarantees:** Critical billing notifications (e.g., "trial expired", "payment failed") are treated identically to social notifications and lack delivery guarantees, but must be processed exactly once.

### Scaling and Business Constraints
* **Decoupling & Real-time:** We must move notifications to asynchronous processing, support exponential backoff retries, and deliver real-time WebSocket push notifications within 2 quarters.
* **10x Scale Target:** The solution must handle a 10x increase in peak traffic (~5,000 req/s) without requiring a complete re-architecture.
* **Team Constraints:** A team of only 6 developers (3 senior, 3 mid-level) with no dedicated DevOps or infrastructure engineer. The team has **zero** experience operating Apache Kafka.
* **Time-to-Value:** The solution must be production-ready and deliver value within 2 weeks of setup and migration work.
* **Budget:** Modest infrastructure budget; cannot afford enterprise-tier managed solutions (e.g., Confluent Cloud) at scale.
* **Critical Guarantee:** Billing-critical notifications require exactly-once semantics.

---

## Decision
We choose **Redis Streams** as the foundational message broker for the notification subsystem.

### Justification

1. **Zero Operational Overhead & Budget Fit:** 
   Our team already operates Redis in production for sessions and rate-limiting. Choosing Redis Streams avoids introducing a new technology to our infrastructure stack. There is no need to provision, configure, or pay for a new database cluster. Managed alternatives like Confluent Cloud are financially unviable, and self-hosting Kafka without a dedicated infrastructure engineer represents a high-risk operational liability.

2. **Compliance with the 2-Week Value Delivery Constraint:**
   By leveraging existing Redis infrastructure and well-documented Python clients (such as `redis-py`), our 6-person team can implement, test, and deploy Redis Streams in production within the 2-week window. Kafka would require a multi-week learning curve, local environment configuration, and complex CI/CD setup.

3. **Performance and Scaling Headroom:**
   Redis Streams operates in-memory with sub-millisecond write and read latencies. A single modest Redis node can comfortably handle over 100,000 operations per second. Our 10x peak scaling target is 5,000 req/s, which falls well within Redis's single-node capabilities.

4. **Robust Consumer Groups and Reliable Delivery:**
   Redis Streams natively supports Consumer Groups (`XGROUP`, `XREADGROUP`). It provides at-least-once delivery guarantees through message acknowledgment (`XACK`) and tracks unacknowledged, stalled, or failed messages via the Pending Entries List (PEL). This allows us to easily build an active claim/retry worker pattern and implement a Dead Letter Queue (DLQ).

5. **Application-Level Exactly-Once Semantics (EOS) for Billing:**
   Since our application utilizes PostgreSQL, we can maintain exactly-once processing for billing events by combining Redis Streams' **at-least-once delivery** with the **Idempotent Consumer pattern**. When a billing notification is dispatched, we will generate a unique `idempotency_key` (e.g., `billing:invoice_id:attempt`). The consumer will execute the notification dispatch and record the success within a PostgreSQL transaction using a unique constraint on the key, or via Redis atomic operations (`SET NX PX`). This robustly ensures that billing notifications are not processed more than once, without the overhead of Kafka's heavy transactional coordinator.

6. **Native WebSocket Integration Path:**
   Redis's high-performance in-memory model and pub/sub capabilities integrate seamlessly with asyncio-based Python WebSocket workers (such as lightweight FastAPI or gevent/Flask-SocketIO nodes), making the real-time WebSocket push requirement straightforward to implement in the upcoming quarters.

---

## Consequences

### Pros (Benefits)
* **Immediate Delivery:** Leverages our existing Redis cluster, enabling the team to start writing application code on Day 1.
* **Sub-millisecond Latency:** High-throughput, low-latency execution ensures that async workers keep queues clear.
* **Operational Simplicity:** Avoids introducing JVM tuning, ZooKeeper/KRaft quorum management, partition rebalancing, and cluster resizing tasks to a small team.
* **At-Least-Once Guarantee:** Messages remain in the stream and PEL until explicitly acknowledged by consumers, preventing message loss during worker crashes.
* **Resource and Cost Efficiency:** Extremely low resource footprint compared to Kafka, keeping our AWS bill within modest limits.

### Cons (Risks & Mitigations)
* **In-Memory Limitations (RAM Volatility):**
  * *Risk:* Redis Streams are stored in RAM. Large, unchecked streams can exhaust memory and cause eviction or crashes.
  * *Mitigation:* We will enforce strict queue trimming using the `MAXLEN ~ <limit>` option (e.g., keeping a rolling log of 100,000 messages) and delete processed notifications. For long-term audit logs, processed notifications will be archived asynchronously to PostgreSQL or S3.
* **Data Loss on Hard Crash:**
  * *Risk:* Redis persistence (RDB/AOF) is typically configured with fsync policies (e.g., `everysec`) that could lose up to one second of data in a catastrophic hardware failure.
  * *Mitigation:* For non-critical notifications, this risk is acceptable. For billing-critical notifications, we will implement the **Transactional Outbox Pattern** in PostgreSQL: notifications are saved to an `outbox` table in the same ACID transaction as the database change, and a publisher process reads from this table and writes to Redis Streams. If Redis crashes, the state is safely reconstructed from PostgreSQL.
* **No Native Distributed Exactly-Once Semantics:**
  * *Risk:* Unlike Kafka, Redis Streams does not provide broker-managed distributed transactions for exactly-once processing.
  * *Mitigation:* We will enforce idempotency directly in the consumer application code using PostgreSQL database transactions and unique indexes, which is standard practice in Python/Flask services.

---

## Alternatives Considered

### Apache Kafka

We rejected Apache Kafka for the following reasons:

1. **Massive Operational Complexity:**
   Kafka is a distributed commit log that requires significant expertise to configure, tune, secure, and monitor. Managing brokers, partition counts, replication factors, and ZooKeeper or KRaft metadata without a dedicated infrastructure engineer would distract our small 6-person team from delivering core product features.

2. **Severe Timeline Violations:**
   The learning curve for configuring producers, consumers, partition assignments, and handling broker failures in Python (using libraries like `confluent-kafka` or `kafka-python`) would make meeting the 2-week delivery target impossible. 

3. **Incompatible Cost Structure:**
   Deploying a resilient, multi-AZ self-hosted Kafka cluster on AWS is resource-intensive and expensive. Standard managed solutions (like AWS MSK or Confluent Cloud) require high minimum spend commitments that exceed our modest budget.

4. **Mismatched Scale:**
   Kafka is built for heavy-duty stream processing, log ingestion, and high-throughput event sourcing (gigabytes per second). For dispatching emails and webhooks at 500 to 5,000 req/s, Kafka is a massive architectural overkill that introduces unnecessary failure domains.
