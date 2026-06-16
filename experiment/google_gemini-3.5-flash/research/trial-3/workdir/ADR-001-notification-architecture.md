# ADR-001: Choice of Messaging Broker for the Notification Subsystem

## Title
ADR-001: Choice of Messaging Broker for the Notification Subsystem

## Status
Proposed

## Context

Our SaaS project management platform currently services 85,000 monthly active users (MAU), generating approximately 2 million tasks per month, with a peak load of ~500 requests per second (req/s) during business hours. 

The current system processes notifications (emails and webhooks) synchronously within the HTTP request cycle of our Python/Flask monolith. This design has introduced severe operational bottlenecks:
1. **Request Timeouts:** Blocking HTTP threads for synchronous notification delivery leads to an average response latency of 800ms, spiking up to 8 seconds during peak hours.
2. **Silent Failures:** External network/provider failures result in dropped notifications since we lack retries and a Dead-Letter Queue (DLQ).
3. **Cascading Failures:** Slow downstream webhook endpoints have twice exhausted our database connection pools, causing total platform outages.
4. **No Delivery Guarantees:** Critical billing notifications (e.g., payment failures, trial expirations) lack at-least-once or exactly-once delivery guarantees.

### Scaling Target
To handle a projected 10x traffic growth (~5,000 req/s peak) and support real-time WebSocket push notifications within two quarters, we must decouple the notification pipeline into an asynchronous, resilient architecture. The new system must support:
- Asynchronous, non-blocking processing
- Retry with exponential backoff and a Dead-Letter Queue (DLQ)
- Strong delivery guarantees: at-least-once delivery for billing events, and exactly-once semantics where feasible

### Constraints
- **Team Size:** 6 engineers (3 senior, 3 mid-level) with zero dedicated infrastructure or DevOps engineers.
- **Technology Familiarity:** Zero experience with Apache Kafka. The team already runs and maintains Redis in production for session management and rate-limiting.
- **Time to Value:** Maximum 2 weeks of setup and migration work before delivering production value.
- **Budget:** Highly modest; managed services like Confluent Cloud are financially unfeasible at our full projected scale.

---

## Decision

We choose **Redis Streams** as the messaging broker for our new asynchronous notification subsystem.

### Justification

Given our technical constraints, team size, and scaling targets, Redis Streams is the only choice that balances high-performance capabilities with near-zero operational overhead. The evaluation of key technical properties demonstrates why Redis Streams is the superior option:

1. **Operational Complexity:**
   - **Redis Streams:** We already run Redis in production for session storage and rate limiting. Adopting Redis Streams introduces zero new infrastructure dependencies, zero additional hosting costs, and requires no new licensing.
   - **Kafka:** Setting up, configuring, and maintaining an Apache Kafka cluster (with Zookeeper or KRaft) is notoriously complex. It requires specialized tuning of JVM memory, partition sizes, replication factors, and log segments. For our 6-person team with no dedicated infrastructure engineer, self-hosting Kafka represents a massive operational risk that could easily result in unstable deployments and outages.

2. **Time to Value and Budget Constraints:**
   - **Redis Streams:** Because our environment is already provisioned and our team is familiar with Redis commands, we can build, test, and deploy the new worker queue using existing Python Redis libraries (e.g., `redis-py`) within days, easily hitting our 2-week deadline.
   - **Kafka:** Zero team experience means weeks of training, provisioning, and integration testing, which would inevitably miss the 2-week window. The modest budget also prohibits using costly managed Kafka alternatives like Confluent Cloud.

3. **Throughput and Scale:**
   - **Redis Streams:** Redis is an in-memory data store capable of processing over 100,000 operations per second on a single modest instance. At our current peak of 500 req/s, and even at our 10x target of 5,000 req/s, Redis Streams will utilize a negligible fraction of its performance envelope, leaving substantial headroom.
   - **Kafka:** Designed for gigabytes-per-second and millions of events, which is far beyond our architectural needs. Introducing Kafka for 5,000 req/s is a textbook case of over-engineering.

4. **Exactly-Once Semantics (EOS):**
   - True exactly-once delivery to external systems (such as SendGrid for emails or arbitrary customer webhook endpoints) is impossible to guarantee solely at the message broker level. If a consumer successfully delivers an email but the network drops before it can acknowledge the broker, the broker will retry and redeliver, resulting in a duplicate.
   - Therefore, exactly-once delivery for critical billing events must be enforced via **application-layer idempotency**.
   - With Redis Streams, we can achieve guaranteed at-least-once transport delivery through consumer group pending lists and explicit acknowledgments (`XACK`). We will handle the "exactly-once" requirement by writing deduplication logic in our Flask consumers, using a distributed lock or unique constraint in PostgreSQL (tracking processed notification/transaction UUIDs). This is the exact same code we would have to write with Kafka; Kafka's internal broker-side transactional guarantees provide no benefit for external HTTP/SMTP side effects.

5. **Consumer Groups and Horizontal Scaling:**
   - Redis Streams provides native consumer group features (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`) that mirror Kafka's design.
   - Multiple Flask worker processes can join a consumer group to load-balance notification processing. If a worker fails mid-execution, its unacknowledged messages are tracked in the Pending Entries List (PEL). A supervisor process or other active workers can inspect the PEL using `XPENDING` and claim/retry the stale messages using `XCLAIM`, eliminating silent failures.

6. **Ordering Guarantees:**
   - Redis Streams guarantees strict chronological ordering of messages inside a stream. Messages are assigned sequential IDs containing a millisecond timestamp and a sequence count (e.g., `1718561342000-0`). This ensures tasks are processed in the order they occurred (e.g., task assigned before task completed).

7. **Message Retention:**
   - Unlike Kafka, which keeps logs on disk indefinitely (or up to a configured time/size limit), Redis Streams is in-memory. Because notifications are transient events that are consumed and acknowledged quickly, we do not need long-term log retention on the broker.
   - We will use dynamic stream capping (`MAXLEN ~ 10000` or `MINID`) during publishers' `XADD` calls to bound memory consumption, ensuring Redis RAM usage remains stable. Historical audit trails of notifications will be written directly to our PostgreSQL read replica instead of the queue.

---

## Consequences

### Pros of choosing Redis Streams:
- **Immediate Value:** Low setup overhead allows deployment of the decoupled architecture within 1–2 weeks.
- **Zero Additional Cost:** Leverages the existing AWS Redis infrastructure with zero extra license or cloud hosting spend.
- **Low Cognitive Overhead:** The team uses existing Python-Redis libraries and Redis operational knowledge.
- **Guaranteed Reliability:** Consumer groups, PEL, and application-level idempotency solve silent failures and provide robust at-least-once delivery.
- **High Performance:** Sub-millisecond latency and effortless scaling up to 10x our current load.

### Cons of choosing Redis Streams:
- **Memory Bound:** Because Redis is in-memory, we must strictly manage memory usage. If we do not cap the stream size (`MAXLEN`), a sudden burst of unconsumed notifications could exhaust Redis RAM and cause session storage or rate limiting to degrade.
- **Lack of Built-In Schema Enforcement:** Unlike Kafka which integrates with schema registries, Redis Streams accepts raw key-value payloads. We must enforce payload schemas at the application layer using libraries like Pydantic.
- **Clustering Limits:** While Kafka natively partitions topics across multiple physical nodes, a single Redis Stream resides on a single Redis master node. While this master can be scaled vertically, we cannot partition a single stream horizontally without manually distributing messages across multiple streams (hash slot partitioning), though this is highly unnecessary for our 5,000 req/s scale.

---

## Alternatives Considered

### Apache Kafka

We evaluated Apache Kafka as our message broker but rejected it for the following reasons:

- **Prohibitive Operational Overhead:** Setting up and managing Kafka requires deep infrastructure expertise. A 6-person team cannot afford to split their focus on JVM tuning, KRaft/Zookeeper cluster health, disk sizing, and rebalancing partitions.
- **Violates 2-Week Constraint:** The setup, learning curve, and migration would take several weeks of dedicated engineering time, delaying the delivery of value far beyond the 2-week limit.
- **Cost Inefficiency:** Self-hosting a reliable, multi-node Kafka cluster on AWS is expensive, and enterprise-grade managed options like Confluent Cloud exceed our modest budget constraints.
- **Excessive Scale/Over-Engineering:** Kafka is designed for real-time ingestion of millions of events per second. Utilizing it for our peak target of 5,000 req/s adds massive architectural complexity with no performance payoff.
- **No Benefit for External Exactly-Once:** Kafka's internal exactly-once transactional semantics do not automatically apply to external side-effects like sending emails or invoking webhooks. Since we still have to implement application-level idempotency, Kafka's major differentiator is neutralized.
