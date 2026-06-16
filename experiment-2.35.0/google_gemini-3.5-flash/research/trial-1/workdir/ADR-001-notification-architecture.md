# ADR-001: Notification Architecture Decoupling

## Status
Proposed

## Context
Our SaaS project management platform is experiencing severe scalability and reliability issues in the notifications module. Currently, we process 85,000 monthly active users and ~2M tasks created per month, with business-hour peaks reaching ~500 req/s. Notifications (emails and webhooks) are processed synchronously within the Python/Flask HTTP request cycle, leading to several critical failures:
1. **Request Timeouts:** Synchronous processing blocks HTTP responses. Average latency is 800ms, spiking to 8s during peak hours.
2. **Silent Failures:** External system outages (email providers, webhook endpoints) cause silent message drops due to the lack of retries or a Dead-Letter Queue (DLQ).
3. **Cascading Failures:** Connection pool exhaustion from slow webhook endpoints has twice triggered cascading outages, taking down unrelated monolith features.
4. **No Delivery Guarantees:** Critical billing notifications (e.g., "trial expired", "payment failed") have no transactional safety or delivery guarantees.

### Scaling Target
- **Decouple Notifications:** Move to asynchronous processing.
- **Resilience:** Support automated retry with exponential backoff.
- **Delivery Guarantees:** Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- **Real-Time Push:** Add real-time WebSocket push notifications within two quarters.
- **Scale:** Handle 10x growth (~5,000 req/s peak during business hours) without re-architecting.

### Key Constraints
- **Team Size:** 6 engineers (3 senior, 3 mid-level) with zero dedicated infrastructure engineers.
- **Existing Tech Stack:** Python/Flask, PostgreSQL, and Redis (used for sessions and rate limiting).
- **Team Experience:** Zero Kafka experience.
- **Timeline:** Setup and migration must deliver business value within 2 weeks.
- **Budget:** Modest. Cannot support costly managed options like Confluent Cloud.

---

## Decision
We will use **Redis Streams** as the message broker for the decoupled notification subsystem. 

### Justification

Given our team's small size, budget constraints, and 2-week delivery timeline, **Redis Streams** is the only viable choice. It meets our scale, reliability, and real-time push requirements with near-zero additional operational overhead.

1. **Throughput and Scale:** At 10x growth, our peak is 5,000 req/s. A single Redis instance easily handles >100,000 operations/sec. Redis Streams will easily absorb peak write volumes with sub-millisecond latencies, well within our performance targets.
2. **Zero Operational Overhead:** We already run Redis in production for sessions and rate-limiting. Using Redis Streams requires zero new infrastructure setup, monitoring, or provisioning.
3. **Rapid Time-to-Value:** Since the team is already familiar with Redis and client libraries (such as `redis-py`), integration can be completed, tested, and deployed to production in less than one week. This easily satisfies our 2-week deadline.
4. **Consumer Groups and Reliability:** Redis Streams natively supports consumer groups (`XGROUP`, `XREADGROUP`), trackable message acknowledgment (`XACK`), and consumer claiming (`XCLAIM`). This allows us to build horizontally scaling, parallel worker processes that safely track and retry failed notification tasks.
5. **Real-time WebSockets integration:** In-memory speed and Redis' native pub/sub capabilities simplify building the real-time WebSocket push notifications scheduled for Q2.
6. **Exactly-Once Semantics (EOS) for Billing:** Pure exactly-once delivery across external APIs (like email and webhook gateways) is mathematically impossible at the broker level alone because external API calls are non-transactional. To achieve exactly-once semantics for billing, we will implement the **Transactional Outbox pattern** using our primary database (PostgreSQL) and match it with idempotent workers in Redis Streams.
   - **Persistence & Integrity:** Billing events will be written to a Postgres `outbox` table in the *same* ACID transaction as the state change. This guarantees at-least-once persistence of the event.
   - **Broker Dispatch:** A lightweight process will tail the outbox and dispatch to a Redis Stream.
   - **Idempotency Guarantee:** Before executing any external API (e.g., sending billing notifications), the consumer worker will attempt to insert a unique message identifier (e.g., `event_uuid`) into a `processed_notifications` ledger table in PostgreSQL. If the insert succeeds, the worker executes the API and calls `XACK`. If the insert fails due to a unique constraint violation, the message is identified as a duplicate and safely ignored.

---

## Consequences

### Pros (Positive Consequences)
- **Minimal Operational Burden:** No new servers to provision, secure, backup, or monitor. We leverage our existing AWS-hosted Redis instance, avoiding JVM tuning, disk provisioning, or cluster management.
- **High Performance:** In-memory writes and reads guarantee sub-millisecond dispatch times, completely removing notification latency from the synchronous HTTP cycle.
- **Advanced Processing Capabilities:** Native consumer groups enable parallel execution, message tracking (Pending Entries List or PEL), and automated dead-letter queues through claiming (`XCLAIM`) and tracking delivery attempts.
- **Cost-Effective:** Zero additional licensing or infrastructure costs. We avoid costly cloud managed Kafka offerings (e.g., Confluent Cloud).

### Cons (Negative Consequences)
- **Memory Consumption:** Redis keeps all active stream data in RAM. Unchecked stream growth can cause out-of-memory (OOM) failures. We must strictly manage memory by capping streams using `XADD` with `MAXLEN` or `XTRIM`, and archive older notifications.
- **Durability Risks:** Unlike Kafka, which writes directly to a disk-based commit log, Redis is primarily an in-memory datastore. In a worst-case failover scenario, up to 1 second of stream data can be lost if AOF (Append Only File) is configured to write `everysec`. 
  - *Mitigation:* Important billing notifications are resilient to this because they are anchored in the PostgreSQL `outbox` table, allowing automatic replay if a Redis data loss occurs.
- **Client Library Ecosystem:** While Python's `redis-py` fully supports Streams, it does not feature the mature, declarative abstractions present in Kafka frameworks. We will need to write custom wrapper code for worker polling, claiming (`XCLAIM`), and error retrying.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following critical reasons:
1. **High Operational Complexity:** Kafka requires managing ZooKeeper/KRaft, broker JVM tuning, disk I/O, partition replication, and complex client-side configurations. Without a dedicated infrastructure engineer, managing this cluster would consume our 6-person team's entire capacity.
2. **Steep Learning Curve:** No engineers on our team have Kafka experience. Acquiring this expertise and establishing local development workflows would take several weeks, violating our 2-week time-to-value constraint.
3. **High Infrastructure Cost:** Self-hosting Kafka with appropriate redundancy (multi-node, multi-AZ) is expensive. Managed solutions like Confluent Cloud or AWS MSK exceed our modest budget.
4. **Over-engineering:** While Kafka scales to millions of events per second and offers robust disk-based message retention, our immediate and 10x scaling targets (up to 5,000 req/s) are easily handled by a single in-memory Redis instance.

*We would have chosen Kafka if:*
- Our team had dedicated platform/SRE engineers.
- Our throughput exceeded 100,000 write operations per second.
- We required multi-week or multi-month message retention directly inside the event stream rather than archiving to Postgres/S3.
- We had a budget to afford a fully managed Confluent Cloud enterprise tier.
