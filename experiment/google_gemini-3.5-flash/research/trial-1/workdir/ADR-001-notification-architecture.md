# ADR-001: Notification Subsystem Architecture

- **Status**: Accepted
- **Date**: 2026-06-23
- **Deciders**: Engineering Team (3 Senior Engineers, 3 Mid-Level Engineers)
- **Context tags**: architecture, notifications, message-broker, scale

## Context

Our SaaS project management platform currently services 85,000 monthly active users (MAUs), processing approximately 2 million task updates/creations per month. During business hours, the system experiences peak loads of ~500 req/s. 

Currently, notifications (emails, webhooks) are processed synchronously within the HTTP request cycle of our Python/Flask monolith. This design introduces severe production issues:
1. **Request Timeouts**: Sending notifications blocks HTTP responses, leading to an average latency of 800ms, spiking to 8 seconds during peak hours.
2. **Silent Failures**: Down stream failures (e.g., email provider or webhook endpoint down) cause notifications to be silently dropped with no mechanism for retry or dead-letter queuing (DLQ).
3. **Cascading Failures**: Slow webhook endpoints have exhausted database connection pools twice this year, resulting in total platform outages.
4. **No Delivery Guarantees**: Critical billing-related notifications (e.g., payment failures, trial expirations) are sent without any delivery guarantees.

We need to decouple notifications into an asynchronous processing model, implement exponential backoff retries, support real-time WebSocket push notifications within 2 quarters, scale to 10x traffic growth (~5,000 req/s at peak) without re-architecting, and guarantee at-least-once delivery for billing events (and exactly-once processing where feasible).

Our operational constraints are highly restrictive:
- **Team**: 6 engineers (no dedicated DevOps or infrastructure engineer).
- **Knowledge**: No Kafka experience on the team today; extensive experience with Python, PostgreSQL, and Redis.
- **Infrastructure**: We already run PostgreSQL (primary/replica) and Redis (for session storage and rate-limiting) on AWS.
- **Timeline**: Must deliver value in less than 2 weeks of setup and migration work.
- **Budget**: Modest; managed enterprise Kafka (e.g., Confluent Cloud) is cost-prohibitive at our scale.

---

## Decision

We will use **Redis Streams** as the underlying message broker and queueing technology for our notification subsystem. 

To achieve exactly-once semantics for critical billing notifications, we will implement the **Idempotent Consumer Pattern** using our existing PostgreSQL database as the deduplication store.

### Justification

1. **Operational Simplicity & Team Velocity**: We already run Redis in production. Adding Redis Streams introduces **zero** new infrastructure dependencies, zero budget increases, and requires no specialized infrastructure engineers. The team can develop, test, and deploy this solution locally and to AWS within the 2-week constraint.
2. **Technical Fit for Scale**: Redis Streams easily handles tens of thousands of write operations per second with sub-millisecond latencies. At our 10x peak scaling target of 5,000 req/s, Redis Streams will operate comfortably, utilizing only a minor fraction of a single Redis node's capacity.
3. **Robust Consumer Group Mechanics**: Redis Streams natively supports Consumer Groups (`XGROUP`, `XREADGROUP`). It tracks pending messages (`XPENDING`), handles consumer failures via consumer claiming (`XCLAIM`), and manages message acknowledgment (`XACK`), guaranteeing **at-least-once delivery** out-of-the-box.
4. **Exactly-Once Delivery Realized Correctly**: True exactly-once delivery to external systems (like sending an email via SendGrid or hitting an external webhook) cannot be achieved solely by any broker (including Kafka), because external HTTP APIs do not participate in broker transactions. Idempotence must be handled at the consumer. By storing processed notification/transaction IDs in our existing PostgreSQL database within ACID transactions, we can guarantee exactly-once processing safely and easily.

---

## Consequences

### Pros (Positive)
- **Minimal Time-to-Value**: No infrastructure to provision, configure, or secure. Developers can begin writing the Python/Flask producer/consumer code immediately.
- **Zero Additional Cost**: Runs on our existing Redis instances, avoiding the high cost of managed queue/log platforms.
- **Low Latency & High Throughput**: Sub-millisecond queuing latencies, keeping resource footprint small.
- **Flexible Scaling**: Unlike Kafka, where the number of active consumers in a consumer group is hard-capped by the number of partitions, Redis Streams allows any number of concurrent consumers to cooperatively process messages from a single stream.
- **Ready for WebSockets**: Redis's lightweight pub/sub and high-performance streams make it the industry-standard backing store for scaling real-time WebSocket connections (e.g., via Socket.io or custom Python ASGI servers) in the upcoming quarters.

### Cons (Negative)
- **In-Memory Constraints**: Redis is in-memory. If the stream grows excessively due to a consumer outage, it could cause Out-Of-Memory (OOM) issues on the Redis node. 
  - *Mitigation*: We will strictly prune the streams using `XADD` or `XTRIM` with the `MAXLEN ~ <threshold>` (e.g., 50,000 events) or `MINID` options. Older processed notifications will be archived to PostgreSQL or S3 if auditing is needed.
- **Data Loss Risk under Extreme Failure**: In the event of a hard physical server crash, Redis's asynchronous persistence (AOF/RDB) could lose up to 1 second of data (depending on configuration).
  - *Mitigation*: For critical billing notifications, we will write to the PostgreSQL database first (using a Transactional Outbox table) before publishing to Redis. If Redis fails, a lightweight cron/worker can poll PostgreSQL and republish missing events.
- **No Native Schema Registry**: Unlike Kafka, Redis Streams does not enforce payload schemas natively.
  - *Mitigation*: We will enforce schema validation in Python at the application layer using libraries like Pydantic.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:

- **Extreme Operational Complexity**: Kafka requires a multi-node cluster, ZooKeeper or KRaft coordination, JVM tuning, partition planning, and complex network configurations. Without a dedicated infrastructure engineer, managing this on AWS would consume significant engineering cycles and introduce major operational risks.
- **Violates Setup Timeline**: Setting up a production-ready, secure Kafka cluster (with monitoring, backup, and local/CI integration) and training a team with zero prior Kafka experience would easily exceed our strict 2-week limit, delaying the delivery of actual business value.
- **Cost Prohibitive**: Managed offerings like AWS MSK or Confluent Cloud have high base fees that violate our modest budget constraints. Self-hosting on EC2 is equally expensive once engineering hours and redundant multi-instance requirements are factored in.
- **Over-engineered for Scale**: While Kafka's infinite scalability and retention are impressive, they are unnecessary. Our peak load (even at 10x) is easily handled by Redis. Furthermore, Kafka's disk-based durability is an anti-pattern for a notification subsystem, where messages are highly transient and do not need to be stored long-term in the queue once acknowledged.
- **Exactly-Once Misconception**: Kafka's transactional exactly-once semantics only apply to processing pipelines entirely contained within Kafka itself (e.g., Kafka to Kafka via Kafka Streams). When consumers trigger real-world, side-effect-heavy actions like email and webhook dispatch, an application-level de-duplication layer in PostgreSQL is still required. Thus, Kafka's built-in transaction system offers no shortcut for our specific problem.
