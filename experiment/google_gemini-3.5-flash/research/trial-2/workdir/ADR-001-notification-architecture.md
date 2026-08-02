# ADR-001: Notification Subsystem Architecture

- **Status**: Proposed
- **Date**: 2026-08-02
- **Deciders**: Technical Lead, Core Engineering Team

## Context

Our SaaS project management platform is currently experiencing performance and reliability bottlenecks in its notification subsystem. We currently handle 85,000 monthly active users, approximately 2 million tasks created per month, and peak traffic of around 500 requests/second during business hours. 

Currently, notifications (emails and webhooks) are sent synchronously inside the HTTP request-response cycle of our Python/Flask monolith. This has led to critical production issues:
1. **Request Timeouts**: Sending notifications blocks HTTP responses, driving average latency to 800ms and causing spikes up to 8 seconds during peak hours.
2. **Silent Failures**: Network issues with email providers or webhooks result in silently dropped notifications, with no retry mechanism or Dead Letter Queue (DLQ).
3. **Cascading Failures**: Slow downstream webhook endpoints have exhausted connection pools twice this year, resulting in platform-wide outages affecting unrelated features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" and "payment failed") are sent without any delivery guarantees.

### Scaling Target and Architectural Goals
- Decouple notifications from the HTTP request cycle using asynchronous message passing.
- Implement reliable retry mechanisms with exponential backoff and a Dead Letter Queue (DLQ).
- Guarantee at-least-once delivery for all notifications, and exactly-once processing for billing-critical events.
- Lay the foundation for real-time WebSocket push notifications within the next two quarters.
- Scale to support a 10x traffic growth (to ~5,000 requests/second at peak and 20 million tasks/month) without requiring a complete re-architecture.

### Constraints
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure/DevOps engineer.
- **Timeline**: The solution must be implemented and deliver value within a strict 2-week window.
- **Operational Footprint**: We already run Redis in production for session storage and rate limiting. There is zero Apache Kafka experience on the team today.
- **Budget**: Modest. We cannot afford a fully managed enterprise Kafka service (e.g., Confluent Cloud) at our projected 10x scale.

---

## Decision

We will use **Redis Streams** as the backbone for our asynchronous notification subsystem. 

### Justification

Redis Streams provides a lightweight, extremely fast, append-only log structure natively supporting consumer groups. It satisfies all of our technical requirements while strictly adhering to our operational and organizational constraints.

1. **Leveraging Existing Operational Knowledge**: The team already runs, monitors, and scales Redis in production. Choosing Redis Streams introduces zero new operational infrastructure, avoiding the high learning curve, setup cost, and cognitive load of a new complex stateful system like Apache Kafka.
2. **Rapid Time-to-Value**: Because the infrastructure is already in place, we can implement the Flask producer-consumer loop using standard, lightweight Python libraries (such as `redis-py` or Celery with a Redis backend) and deploy to production within the 2-week deadline.
3. **Extremely High Throughput & Low Latency**: Being an in-memory data structure, Redis handles 100,000+ operations/second per core with sub-millisecond latencies. At our 10x target peak of 5,000 requests/second, a single Redis instance will comfortably ingest and distribute notification events with minimal resource utilization.
4. **Built-in Consumer Groups (`XGROUP`)**: Redis Streams supports robust consumer group abstractions. This allows us to scale out worker processes (running on our existing 4 web servers or separate worker containers) to process notifications in parallel, track message assignments via Pending Entries Lists (PEL), and safely recover or retry failed messages.
5. **Practical Exactly-Once Semantics**: By pairing Redis Streams' unique, deterministic message IDs with PostgreSQL's ACID transactions (using a simple deduplication table and unique constraint on `event_uuid` in our Flask monolith), we can achieve robust exactly-once delivery for billing-critical events without the extreme architectural complexity of Kafka transactions.

---

## Consequences

### Positive (Pros)
- **Zero New Infrastructure**: No additional servers, clusters, or managed services to provision or pay for. It runs on our existing Redis footprint.
- **Sub-Millisecond Performance**: In-memory reads and writes guarantee that task updates are decoupled from the Flask request-response cycle instantly (typically < 1ms), immediately resolving our 800ms request latency bottleneck.
- **Simple Failure Recovery**: Consumer group commands (`XPENDING` and `XCLAIM`) provide a direct, clean mechanism to implement exponential backoffs, retries, and dead-letter queues (DLQ) directly in our Python codebase.
- **WebSocket-Ready**: Redis's high performance and Pub/Sub compatibility make it the perfect backend to power our real-time WebSocket push notification architecture scheduled for Q4.
- **Low Cost**: Highly cost-effective as it utilizes existing resources, avoiding the expensive premium tier of managed Kafka clusters.

### Negative (Cons)
- **Memory Overhead**: Redis is an in-memory database. If consumer workers lag or downstream external APIs (emails, webhooks) experience prolonged outages, the stream will grow and consume RAM. 
  - *Mitigation*: We must strictly use capped streams via `XADD stream MAXLEN ~ 100000` to prevent memory exhaustion. Once notifications are processed and archived in our PostgreSQL database, they do not need to persist in RAM.
- **Data Persistence Risk**: Unlike Kafka, which commits every message to disk immediately and replicates across distributed nodes by default, Redis's persistence (RDB/AOF) trade-offs mean there is a marginal risk of losing in-flight notifications in a catastrophic cluster crash.
  - *Mitigation*: Enable AOF (Append-Only File) with `appendfsync everysec` on our production Redis instance, and use PostgreSQL as the source-of-truth for state. High-value billing events should be committed to PostgreSQL first, then dispatched to the stream.

---

## Alternatives Considered

### Apache Kafka

We evaluated Apache Kafka as it is the industry standard for high-throughput, distributed event streaming.

* **Throughput**: Unmatched disk-bound throughput and batching capabilities. (Extremely suitable for our 10x scaling target, though vastly over-engineered for 5,000 req/s).
* **Ordering Guarantees**: Guarantees order *within a partition* based on message keys. If a rebalance occurs, ordering can temporarily be disrupted during consumer state transitions.
* **Message Retention**: Outstanding. Stores messages on disk, enabling multi-day or infinite retention without memory pressure.
* **Consumer Groups**: Highly mature partition assignment and automatic rebalancing across consumer group nodes.
* **Exactly-Once Semantics (EOS)**: Supported natively via Kafka transactions. However, this relies on a complex transaction coordinator and is hard to configure, especially with standard Python microservices.
* **Operational Complexity & Costs**: **Extremely High**. Running Kafka requires managing a distributed cluster (with ZooKeeper or KRaft), tuning JVM parameters, managing disk I/O, and setting up complex partitioning/replication schemes. 

#### Why Rejected:
Given our team of 6 engineers with no dedicated DevOps specialist, adopting Kafka represents a severe operational hazard. Setting up, securing, and testing a production-ready Kafka cluster would completely consume our 2-week migration budget and introduce massive ongoing maintenance overhead. Managed solutions (e.g., Confluent Cloud) are cost-prohibitive for our current modest budget. Furthermore, because our consumer workers eventually talk to external network APIs (emails, webhooks), we would still have to write deduplication logic in Python, neutralizing Kafka's native EOS advantages.

### Comparison Table

| Property | Redis Streams | Apache Kafka | Winner for Us |
| :--- | :--- | :--- | :--- |
| **Throughput** | High (In-Memory, 100k+ ops/s) | Ultra-High (Disk-bound batching) | **Redis Streams** (More than sufficient for our 5k req/s target) |
| **Ordering** | Monotonic FIFO per stream key | Key-to-Partition hashing order | **Redis Streams** (No partition rebalance edge cases) |
| **Retention** | Limited (RAM-bound, requires capping) | Excellent (Disk-bound, highly durable) | **Apache Kafka** (Though capping mitigates Redis's RAM limits) |
| **Consumer Groups** | Native (`XREADGROUP`/`XPENDING`) | Native (Automatic partition rebalance) | **Tie** |
| **Exactly-Once** | Deduplication via Postgres + Stream IDs | Native transaction APIs | **Redis Streams** (Far simpler application-level implementation) |
| **Ops Complexity** | Very Low (Existing Infra) | Very High (Requires ZooKeeper/KRaft) | **Redis Streams** (Crucial given 6-person team, 2-week budget) |
| **Estimated Cost** | $0 (Leveraging existing Redis) | High (Infrastructure/SaaS licensing) | **Redis Streams** |
