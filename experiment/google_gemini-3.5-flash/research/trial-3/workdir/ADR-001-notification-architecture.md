# Title: Notification Subsystem Architecture - Redis Streams vs. Apache Kafka

## Status
Proposed

## Context

### Problem Statement
Our SaaS project management platform is experiencing critical performance and reliability issues within the notifications module. Currently, the module sends emails and webhooks synchronously inside the Python/Flask HTTP request cycle. With 85,000 monthly active users and peak loads reaching ~500 requests per second, this synchronous execution has led to:
1. **Severe Request Latency & Timeouts**: The average request latency has degraded to 800ms, with spikes up to 8 seconds during peak hours due to blocking notification dispatches.
2. **Silent Delivery Failures**: When third-party email providers or client webhook endpoints are down, notifications are silently dropped because there is no retry mechanism or Dead Letter Queue (DLQ).
3. **Cascading Failures & Outages**: Webhook target timeouts have repeatedly exhausted Flask's database/connection pools, leading to two major system-wide outages this year.
4. **Lack of Delivery Guarantees**: Critical billing notifications (e.g., trial expiration, payment failures) require exactly-once processing semantics to prevent duplicate billing communications or silent account lockouts, which the current synchronous model cannot guarantee.

### Scaling & Operational Target
To resolve these issues and support the next phase of growth, the notification subsystem must be redesigned to:
- Decouple notification dispatching from the synchronous HTTP request-response cycle.
- Support robust retries with exponential backoff and DLQ routing.
- Guarantee at-least-once delivery for general notifications and exactly-once processing semantics for billing events.
- Support real-time WebSocket push notifications within 2 quarters.
- Scale to handle a 10x traffic increase (up to 5,000 req/s peak) without requiring immediate re-architecting.

### Key Constraints
- **Team Size**: A small engineering team of 6 people (3 senior, 3 mid-level) with **no dedicated infrastructure or DevOps engineer**.
- **Existing Infrastructure**: We already run and operate Redis in production for session storage and rate limiting.
- **Experience Gap**: The team has **zero operational or development experience with Apache Kafka**.
- **Timeframe**: Setup, integration, and deployment of the solution must take **no more than 2 weeks** to begin delivering production value.
- **Budget Constraints**: Modest budget. Managed Confluent Cloud or enterprise Kafka hosting is cost-prohibitive at our scale.
- **Transactional Consistency**: Exactly-once semantics must be maintained for critical billing events.

---

## Decision

We will use **Redis Streams** as the backbone messaging queue and streaming engine for our notification subsystem, paired with **PostgreSQL Transactional Outbox Pattern** to guarantee exactly-once processing for billing-critical events.

### Justification Summary
Redis Streams meets all our scale requirements (comfortably handling over 5,000 req/s at sub-millisecond latency) with **zero additional operational overhead**, as we already run and maintain Redis in production. Choosing Redis Streams allows our 6-person team to meet the strict 2-week time-to-value constraint. Conversely, Apache Kafka was rejected due to its extreme operational complexity, lack of team familiarity, high hardware costs, and the inability to deploy a production-ready cluster within the 2-week budget.

---

## Consequences

### Positive (Pros)
1. **Minimal Operational Overhead**: Since we already operate and monitor Redis in production, we do not need to provision new infrastructure, configure new clustering mechanisms, or manage new security/network topologies.
2. **High Throughput and Ultra-Low Latency**: Because Redis is an in-memory database, it supports tens of thousands of write/read operations per second with sub-millisecond latencies. This easily absorbs our current peak of 500 req/s and our 10x target of 5,000 req/s on a single modest Redis node.
3. **Native Consumer Group Support**: Redis Streams natively supports Consumer Groups (`XGROUP`, `XREADGROUP`). It automates message distribution across workers, maintains tracking of pending messages (`XPENDING`), and allows active workers to claim dead workers' messages (`XCLAIM`), ensuring no message is lost.
4. **Immediate Time to Value**: The team can use Python's mature `redis-py` library to integrate Redis Streams immediately, ensuring we hit our 2-week delivery deadline.
5. **Cost Efficiency**: No new licenses or expensive managed infrastructure are required. We can leverage our existing Redis deployment or scale it up vertically for a fraction of the cost of a managed Kafka cluster.

### Negative (Cons)
1. **Memory Bounds**: Redis is entirely in-memory. If consumer workers crash or fall behind, memory usage will grow linearly. We must actively manage queue depth using stream trimming (`XADD` with `MAXLEN ~` or `XTRIM`) to avoid out-of-memory (OOM) crashes.
2. **At-Least-Once Native Guarantee**: Like most messaging systems, Redis Streams natively guarantees *at-least-once* delivery (via ack tracking using `XACK`). To achieve *exactly-once* processing, we must implement deduplication logic on the consumer side (detailed below).
3. **No Native Long-Term Message Retention**: Redis Streams is not designed to be a durable, multi-week event store like Kafka. Once messages are acknowledged and trimmed, they are permanently removed. This is acceptable for transient notifications but requires critical events to be archived elsewhere (e.g., PostgreSQL).

### Follow-Ups & Mitigations
- **Memory Monitoring**: Set up strict alert thresholds on Redis memory usage and stream lengths.
- **Stream Trimming**: Apply approximate trimming (`MAXLEN ~ 100000`) on every write to cap memory footprint.
- **Exactly-Once Implementation**: To guarantee exactly-once semantics for billing notifications:
  1. Writers will write billing notifications to a PostgreSQL `outbox_events` table under the same transaction as the billing update.
  2. A background worker or CDC process will stream these events to Redis.
  3. Consumers will use a unique `idempotency_key` (e.g., event UUID) checked against a PostgreSQL `processed_notifications` table within a transaction before sending the email/webhook, guaranteeing exactly-once execution.

---

## Alternatives Considered

### Apache Kafka

We extensively evaluated **Apache Kafka** but rejected it for the following reasons:

1. **Extreme Operational Complexity**: Kafka requires running and maintaining a cluster of Kafka brokers, alongside ZooKeeper or KRaft metadata nodes. This demands partition layout planning, JVM garbage collection tuning, disk and network bandwidth provisioning, and complex replication/failover configurations. With a 6-person team and no dedicated infrastructure engineer, self-hosting Kafka is an extreme risk to our operational stability.
2. **No Team Experience**: The team has no familiarity with Kafka's architectural concepts (consumer group coordinator protocols, partition rebalancing storms, offset management). Up-skilling the team would take weeks, making a 2-week delivery window impossible.
3. **Cost Constraints**: High availability in Kafka requires at least 3 brokers and 3 ZooKeeper/KRaft nodes, leading to high baseline server costs. A managed solution like Confluent Cloud was evaluated but rejected due to our modest budget constraints.
4. **Throughput Mismatch**: Kafka is designed to ingest millions of events per second. Our 10x target is 5,000 req/s, which is a scale that Redis can handle easily on a single standard node. Using Kafka for this volume represents a massive over-engineering effort.
5. **Exactly-Once Complexity**: While Kafka supports native Exactly-Once Semantics (EOS), setting up Kafka transactions in Python is notoriously complex, brittle, and does not automatically extend to state updates in our relational PostgreSQL database. We would still require consumer-side database-level idempotency checks.

### Detailed Technical Comparison

| Feature / Property | Redis Streams | Apache Kafka | Project Constraint & Target Fit |
| :--- | :--- | :--- | :--- |
| **Throughput & Latency** | **Winner**: ~50k+ ops/sec per node, sub-millisecond latency (in-memory). | Extreme scale (millions ops/sec), but higher latency due to disk writes and batching. | Both exceed our 10x peak target (5,000 req/s). Redis provides lower latency. |
| **Ordering Guarantees** | Strict global FIFO order per stream key naturally. | Strict order only within a partition; requires partition key routing. | Notifications must be delivered in order of task updates (e.g., creation before completion). Both support this. |
| **Message Retention** | Volatile (In-Memory). Must be explicitly trimmed to avoid OOM. | **Winner**: Durable (Disk-Backed). Configurable retention (days, weeks, forever) without memory pressure. | Real-time notifications are ephemeral; long-term durability is not a primary requirement. We can persist audit logs in Postgres. |
| **Consumer Groups** | Supported natively (`XGROUP`, `XACK`, `XPENDING`, `XCLAIM`). Light rebalancing. | **Winner**: Enterprise-grade consumer groups, partition ownership, and automatic rebalancing. | Both support distributing notifications to a pool of concurrent workers. |
| **Exactly-Once Semantics** | Supported via client-side deduplication (e.g., Transactional Outbox + Postgres Inbox). | Supported natively via internal transaction coordinator, but complex to implement in Python. | **Critical Constraint**: Both require client coordination when modifying our Postgres DB. Redis + Postgres Outbox is simpler. |
| **Operational Complexity** | **Winner**: Extremely Low. Already in production. 1-2 hours of config. | Extremely High. Requires broker/KRaft cluster setup, JVM tuning, disk management. | **Hard Constraint**: 6-person team with no infra engineer cannot afford to operate Kafka. |
| **Time to Value** | **Winner**: < 2 days of setup. Integrates with existing Redis. | 2–4 weeks minimum for clustering, integration, testing, and deployment. | **Hard Constraint**: Must deliver value in ≤ 2 weeks. Kafka fails this constraint. |
| **Budget Fit** | **Winner**: Zero additional cost. | Expensive self-hosted hardware footprint or costly managed Confluent Cloud. | **Hard Constraint**: Must fit a modest startup budget. |
