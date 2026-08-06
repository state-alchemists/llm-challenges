# ADR-001: Notification Subsystem Architecture Decision Record

## Status
Accepted

## Context
Our project management platform currently processes notifications synchronously within the HTTP request cycle (`system_context.md:16`), which causes request timeouts (averaging 800ms, spiking to 8s during peak hours), silent failures with no retry mechanism, connection pool exhaustion leading to cascading failures, and a lack of delivery guarantees for critical billing events (`system_context.md:20-25`). 

To address these pain points, we must transition to an asynchronous notification subsystem that meets the following scaling targets and constraints:
- **Scale**: Support current metrics (85,000 MAU, ~2M tasks/month, peak ~500 req/s) and scale to 10x traffic (~5,000 req/s, ~20M tasks/month) without re-architecting (`system_context.md:6-8,34`).
- **Functionality**: Decouple notifications from the web request cycle, support retry with exponential backoff, support real-time WebSocket push notifications within two quarters, and guarantee at-least-once delivery for billing events (`system_context.md:30-33`).
- **Resource Constraints**: 
  - Engineering team of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer (`system_context.md:38`).
  - No prior Apache Kafka experience on the team (`system_context.md:40`).
  - Existing Redis instance currently used in production for sessions and rate limiting (`system_context.md:39`).
  - Maximum of 2 weeks setup and migration time before delivering business value (`system_context.md:41`).
  - Modest budget (cannot afford fully managed Confluent Cloud at scale) (`system_context.md:42`).
  - Requirement to maintain exactly-once semantics for billing notifications (`system_context.md:43`).

We must evaluate two message brokers to act as the core of this asynchronous notification architecture: **Apache Kafka** and **Redis Streams**.

---

## Decision
We choose **Redis Streams** as the architectural foundation for our notification subsystem. 

### Justification

Redis Streams provides a lightweight, highly performant, and operational-friendly log structure that meets all of our functional requirements while fitting perfectly within our severe operational, budget, and timeline constraints.

1. **Alignment with Team Capacity & Setup Time**:
   Our 6-person team has zero Kafka experience (`system_context.md:38,40`) and no infrastructure engineer. Setting up a production-ready, highly available Apache Kafka cluster (including managing ZooKeeper or KRaft metadata, configuring partition replication, broker JVM tuning, and setting up monitoring) is extremely complex. This would easily exceed our 2-week setup limit (`system_context.md:41`). In contrast, we already run and operate Redis in production (`system_context.md:39`). Leveraging Redis Streams requires zero new infrastructure provisioning, negligible learning curve, and can be integrated within days using the standard Python client (`redis-py`).

2. **Cost & Infrastructure Budget**:
   Managed Kafka (e.g., Confluent Cloud) is cost-prohibitive for our modest budget (`system_context.md:42`), and hosting a self-managed Kafka cluster on AWS (EC2/MSK) carries high baseline infrastructure costs and massive indirect labor costs (maintenance, patching, on-call). Redis Streams uses our existing infrastructure or can scale with cheap, incremental memory upgrades, staying well within our budget.

3. **Performance and Throughput Sufficiency**:
   At a peak of 500 req/s, scaling to 5,000 req/s under 10x growth (`system_context.md:8,34`), Redis easily satisfies our throughput requirements. A single Redis instance can process upwards of 50,000 to 100,000 writes per second with sub-millisecond latencies. Kafka’s immense horizontal scalability is vastly over-engineered for our scale and does not justify its operational penalty.

4. **Reliability & Delivery Guarantees**:
   Redis Streams natively supports Consumer Groups, Message Acknowledgement (`XACK`), and Pending Entries Lists (`PEL`) to track unacknowledged messages. This allows us to guarantee at-least-once delivery and easily build a retry worker with exponential backoff by querying the PEL (`XPENDING`) and re-processing timed-out items.

5. **Exactly-Once Semantics (EOS) Implementation**:
   For billing notifications (`system_context.md:43`), true exactly-once semantics cannot be achieved by the message broker alone; it requires coordination with the destination storage. Because our backend is a Python/Flask monolith backed by a PostgreSQL database (`system_context.md:12-13`), we can achieve exactly-once semantics at the consumer level by implementing **idempotent consumers** within PostgreSQL transactions.
   - Consumers will read messages from Redis Streams.
   - Within a single PostgreSQL transaction, the consumer will check if the unique notification ID (or billing transaction ID) has already been processed (using an idempotent deduplication table, e.g., `processed_notifications` with a primary key constraint).
   - If not processed, the consumer executes the business logic (e.g., recording the notification state, preparing email/webhook payload), inserts the ID into the deduplication table, and commits the database transaction.
   - Finally, the consumer sends the acknowledgement (`XACK`) to Redis Streams. If the consumer crashes before `XACK`, the message is re-delivered but rejected by the PostgreSQL database constraint, ensuring exactly-once processing.

6. **WebSockets Readiness**:
   Redis natively excels at pub/sub and in-memory operations. We can easily utilize Redis Streams or Redis Pub/Sub in the future (within the 2-quarter target) to push real-time events to WebSocket workers, whereas Kafka integration with WebSockets in Python requires significantly heavier framework support.

---

## Consequences

### Pros (Benefits)
- **Extremely Low Operational Overhead**: No new infrastructure components to install, configure, patch, or monitor.
- **Ultra-low Latency**: Redis processes stream reads and writes in-memory with sub-millisecond latency.
- **Rapid Time-to-Value**: Python's `redis-py` has native support for streams (`XADD`, `XREADGROUP`, `XACK`, `XPENDING`). We can deliver a working proof of concept in less than a week.
- **Resource Efficiency**: Negligible increase in RAM/CPU usage on our existing Redis instances, keeping infrastructure costs flat.
- **Strict FIFO Ordering**: Strictly preserves message entry order per stream, ensuring sequential processing where required.

### Cons (Risks and Mitigations)
- **Memory Consumption**: Redis is an in-memory database. Storing millions of messages indefinitely in a stream will deplete RAM.
  - *Mitigation*: We will enforce capped streams using the `MAXLEN` option during `XADD` (e.g., maintaining a sliding window of the last 100,000 notifications) or use explicit trimming (`XTRIM`). Historical notification logs will be archived to our persistent PostgreSQL database or cold storage (S3) once processed and acknowledged.
- **Data Persistence Risk**: By default, Redis replicates asynchronously to replica nodes and persists to disk (AOF/RDB) asynchronously, which introduces a microscopic risk of data loss on sudden master node failure.
  - *Mitigation*: For critical billing notifications, we will configure the Redis instance with Append-Only File (AOF) persistence set to `appendfsync everysec` (or `always` if extreme durability is required for specific flows). We can also utilize the `WAIT` command to ensure writes are replicated to our Redis replica before confirming receipt to the client.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Apache Kafka is a distributed, partitioned, and replicated commit log service designed for processing trillions of events per day. While it is the industry standard for large-scale event-driven architectures, we rejected it for the following reasons:

- **Unjustifiable Operational Complexity**: Kafka requires significant specialized expertise to run reliably. Without a dedicated infrastructure engineer (`system_context.md:38`), our 6-person team would spend a disproportionate amount of time on cluster administration, partition management, rebalancing issues, and JVM tuning instead of building core product features.
- **Failure to Meet Timeline Constraints**: Zero Kafka experience on the team (`system_context.md:40`) means setup, client integration (using complex Python drivers like `confluent-kafka` or `kafka-python`), testing, and operational runbook drafting would comfortably exceed our strict 2-week limit (`system_context.md:41`).
- **High Financial Cost**: Managed Kafka solutions like Confluent Cloud or AWS MSK are too expensive for our modest budget (`system_context.md:42`), and running self-hosted Kafka brokers is operationally too risky.
- **Ecosystem Mismatch**: Exactly-Once Semantics (EOS) in Kafka relies on its transactional API, which is primarily mature and straightforward in the Java/JVM ecosystem (Spring Cloud Stream, Kafka Streams). Implementing Kafka transactional producers and consumers in a Python/Flask monolith is complex, poorly documented, and prone to implementation bugs.
- **Scale Overkill**: Our 10x target of 5,000 req/s does not require the massive multi-node horizontal scalability that Kafka offers at the cost of high latency and complexity.
