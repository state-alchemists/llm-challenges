# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

## Context

We run a SaaS project management platform with 85,000 monthly active users and ~2M tasks created per month, experiencing a peak load of ~500 requests per second (req/s) during business hours. Our current architecture consists of a Python/Flask monolith backend, a PostgreSQL database (single primary with one read replica), 4 web servers on AWS behind nginx, and Redis (currently utilized for session storage and rate limiting).

Currently, notifications (emails and webhooks sent when tasks are updated, assigned, or completed) are handled synchronously inside the HTTP request cycle. This has introduced critical production issues:
1. **Request Timeouts**: Sending notifications synchronously blocks the HTTP response, driving average latency to 800ms and causing spikes of up to 8s during peak hours.
2. **Silent Failures**: Notification delivery has no retry mechanism or dead-letter queue (DLQ); downstream failures (e.g., third-party email providers or webhook endpoints) result in silently dropped notifications.
3. **Cascading Failures**: Slow external webhook endpoints have caused connection pool exhaustion in our monolith twice this year, taking down unrelated features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" and "payment failed") are treated the same as transient task updates, with no delivery guarantees.

### Scaling & Operational Constraints
- **10x Scaling Target**: The new system must support a 10x traffic growth (reaching peak loads of ~5,000 req/s and ~20M tasks/month) without needing another complete re-architecture.
- **Technical Goals**: Decouple notifications from the request-response cycle, support exponential backoff retries, guarantee at-least-once delivery for billing events (exactly-once where feasible), and prepare the infrastructure to support real-time WebSocket push notifications within two quarters.
- **Resource Constraints**:
  - **Engineering Team**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure or DevOps engineer.
  - **Budget**: Modest; we cannot afford high-tier managed services like Confluent Cloud at our target scale.
  - **Timeframe**: The solution must require less than 2 weeks of setup and migration work before delivering production value.
  - **Technology Familiarity**: We already run Redis in production for sessions and rate limiting. The team has zero experience operating or developing with Apache Kafka.

---

## Decision

We will use **Redis Streams** as the messaging broker for our notification subsystem, combined with an **At-Least-Once Delivery + Consumer-Side Idempotency** pattern.

This decision leverages our existing production Redis infrastructure to solve all immediate latency, reliability, and cascading failure issues while keeping operational complexity and cloud costs at near-zero. This choice enables our small, 6-person team to meet the strict 2-week time-to-value constraint and easily handle the 10x scaling target (5,000 req/s peak load).

---

## Consequences

### Positive (Pros)
- **Zero New Infrastructure Overhead**: Since Redis is already running in our production AWS environment, we don't need to provision, secure, configure, or monitor any new database servers or clusters.
- **Rapid Time-to-Value**: The team can utilize standard, lightweight Python clients (e.g., `redis-py`) to build the producer-consumer pipeline. It requires no steep learning curve and will easily be in production within the 2-week limit.
- **Ultra-High Performance & Low Latency**: Operating completely in-memory, Redis Streams handles tens of thousands of write and read operations per second with sub-millisecond latencies. It will easily ingest the targeted 10x peak traffic (5,000 req/s) with minimal CPU and memory footprints.
- **Native Consumer Groups**: Redis Streams supports robust consumer groups (`XGROUP`, `XREADGROUP`). Multiple parallel background consumer workers can pull from the same stream, assign message ownership, and dynamically scale out processing.
- **Seamless WebSocket Integration**: Redis is highly optimized for pub/sub and real-time streaming, aligning perfectly with our Q2 target of delivering real-time push notifications over WebSockets.
- **Low Cost**: We avoid the massive compute, memory, and license costs associated with running a self-hosted Kafka cluster, as well as the high subscription pricing of managed event platforms.

### Negative (Cons & Mitigations)
- **RAM-Bound Storage Risk**: Because Redis is an in-memory database, an outage in consumer workers or an unexpected spike in message volume could lead to unbound RAM growth and Out-Of-Memory (OOM) failures.
  - *Mitigation*: We will strictly enforce stream length capping using the `MAXLEN ~ 10000` argument on every `XADD` operation. Furthermore, we will keep message payloads minimal (passing only resource IDs and lightweight metadata in the stream, while loading heavy email templates or webhook payloads from PostgreSQL/S3 during worker execution). We will also set up CloudWatch alarms on Redis memory usage.
- **Durability Constraints**: In a worst-case hardware crash, Redis's standard asynchronous persistence (AOF with `appendfsync everysec`) can result in a loss of up to 1 second of buffered stream data.
  - *Mitigation*: For transient task notifications, 1-second loss under catastrophic failure is an acceptable trade-off. For critical billing notifications (e.g., "payment failed"), we will implement the **Transactional Outbox Pattern**: the Flask monolith will write the notification record to a `billing_notifications` table in PostgreSQL within the same database transaction as the billing state change. A lightweight publisher will then read from this table and push to Redis Streams, guaranteeing zero data loss.
- **Manual Consumer Failover**: Redis Streams consumer groups track pending messages via a Pending Entries List (PEL) but do not feature automated partition rebalancing like Kafka when a consumer worker dies.
  - *Mitigation*: We will implement a lightweight background process in our Python consumer workers that routinely polls `XPENDING` and uses `XCLAIM` to reclaim and re-process messages that have been stuck in a pending state longer than our processing visibility timeout (e.g., 30 seconds).

---

## Alternatives Considered

### Apache Kafka
Apache Kafka was evaluated as a high-throughput, highly durable alternative but was rejected due to several misalignments with our team size and constraints:

- **Extreme Operational Complexity**: Kafka requires a KRaft cluster or a dedicated ZooKeeper ensemble, JVM tuning, partition configuration, replication factor management, and disk-space alert handling. Without a dedicated infrastructure engineer on our 6-person team, self-hosting Kafka would be an immense operational liability and would distract our senior developers from core product features.
- **Budgetary Constraints**: Running a self-hosted, production-ready, highly available Kafka cluster on AWS (minimum 3 brokers for quorum, plus storage and backup overhead) exceeds our modest budget. Managed alternatives like Confluent Cloud are also cost-prohibitive at our 10x scaling target.
- **Violation of Time Constraints**: Setting up Kafka, designing the schema registry, mastering its complex API, and integrating it into our Flask monolith would take far longer than our 2-week limit, pushing back time-to-value by months.
- **Overkill Throughput**: Kafka is engineered for millions of events per second. Our 10x peak target of 5,000 req/s is easily handled by Redis Streams in-memory. Kafka's massive scale-out benefits are unnecessary for our SaaS workload.
- **Complexity of Exactly-Once Semantics (EOS)**: While Kafka natively supports transactional messages and idempotent producers to achieve EOS, implementing and testing this within a Python monolith using `confluent-kafka-python` is highly complex and error-prone. A simpler, more reliable way to achieve exactly-once semantics for billing in our stack is to combine Redis Streams' at-least-once delivery with standard consumer-side database constraints (e.g., PostgreSQL unique constraints on idempotent request keys).

---

## Technical Comparison Matrix

| Technical Property | Redis Streams (Chosen) | Apache Kafka (Rejected) | Impact & Justification for Choice |
| :--- | :--- | :--- | :--- |
| **Throughput** | High (tens of thousands of operations/sec per node in-memory). Easily meets 5,000 req/s. | Extremely high (millions of events/sec across multiple brokers). | Redis Streams has more than enough throughput for our 10x growth targets with significantly lower resource usage. |
| **Ordering Guarantees** | Strict message ordering within a single stream based on sequential timestamp-based IDs. | Partition-level ordering based on message routing keys. | Both options meet our ordering requirements (e.g., ordering task updates sequentially). |
| **Message Retention** | RAM-bound. Relies on stream trimming (`MAXLEN`) and consumer deletion/acknowledgment. | Disk-bound. Configurable retention by time (e.g., 7 days) or total storage size. | Redis RAM is expensive, but capping streams makes RAM usage deterministic. Ephemeral notifications do not need long-term broker storage. |
| **Consumer Groups** | Supported natively (`XGROUP`, `XREADGROUP`). Tracking via Pending Entries List (PEL). | Highly mature. Automated partition assignment, dynamic consumer rebalancing, and committed offsets. | Kafka's consumer groups are more automated, but Redis's consumer groups are simpler to debug and sufficient when paired with basic `XCLAIM` logic. |
| **Exactly-Once Semantics (EOS)** | Handled via **At-Least-Once Delivery + Idempotency**. Message deduplication relies on database/cache checks. | Supported natively via transaction coordinators and idempotent producers. | Kafka's native EOS is extremely complex in Python. Standard client-side idempotency using PostgreSQL/Redis is simpler, faster, and less error-prone. |
| **Operational Complexity** | **Very Low**. Redis is already in production. Zero setup cost, zero new server overhead. | **Very High**. Requires cluster coordination (KRaft/ZooKeeper), JVM administration, and partition planning. | Redis Streams is the only option that fits our 6-person team with no dedicated infrastructure engineer. |
