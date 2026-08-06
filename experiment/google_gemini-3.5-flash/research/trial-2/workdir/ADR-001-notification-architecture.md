# ADR-001: Choice of Notification Subsystem Architecture

## Status
Proposed

## Context
The project management platform has grown to support 85,000 monthly active users and ~2 million task creations per month, experiencing a peak traffic volume of ~500 requests per second (req/s) during business hours. 

Historically, the notifications module (responsible for dispatching emails and webhooks upon task updates, assignments, and completions) has been executed synchronously inside the HTTP request cycle of our Python/Flask monolith. This design has introduced severe operational and reliability issues:
1. **Request Timeouts**: Sending notifications synchronously blocks the HTTP response, driving average request latency to 800ms, with spikes up to 8s during peak traffic.
2. **Silent Failures**: The system lacks a retry mechanism or Dead Letter Queue (DLQ). If an external email provider or webhook target is down, the notification is silently lost.
3. **Cascading Failures**: Slow downstream webhook targets have twice caused connection pool exhaustion, bringing down unrelated parts of the monolith.
4. **No Delivery Guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") have no transactional delivery guarantees, which poses financial and compliance risks.

To address these pain points, we need to achieve the following scaling targets:
- Decouple notification delivery from the HTTP request-response cycle into an asynchronous worker pipeline.
- Implement reliable retry mechanisms with exponential backoff.
- Guarantee at-least-once delivery for general notifications, and exactly-once delivery for billing-critical events.
- Support real-time WebSocket push notifications within the next two quarters.
- Scale to handle a 10x traffic increase (up to ~5,000 req/s at peak) without requiring an architectural overhaul.

However, our architecture decisions are bound by the following strict operational constraints:
- **Engineering Resources**: A team of 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure or DevOps engineer.
- **Operational Familiarity**: The team already operates Redis in production (used for session storage and rate limiting) but has zero operational experience with Apache Kafka.
- **Time-to-Value**: The notification subsystem solution must be implemented, tested, and delivering business value within 2 weeks.
- **Budgetary Constraints**: A modest budget that cannot support managed enterprise platforms (such as full-scale managed Confluent Cloud) today.

We evaluated two potential messaging technologies to serve as the core of our asynchronous notification broker: **Apache Kafka** and **Redis Streams**.

## Decision
We will use **Redis Streams** as the messaging engine for our notification subsystem. 

By utilizing our existing, production-proven Redis deployment, we can immediately implement a highly scalable, reliable, asynchronous event queue that can be fully engineered, integrated, and deployed within our 2-week deadline.

### Technical Justification

#### 1. Operational Complexity & Resource Alignment
Our team of 6 has no dedicated infrastructure engineer. Operating an Apache Kafka cluster in-house is an immense undertaking, requiring fine-tuning of JVM settings, managing KRaft/Zookeeper, configuring disk-write barriers, and executing complex broker upgrades. Managed alternatives like Confluent Cloud are cost-prohibitive under our current budget. 

In contrast, Redis is already running in production. Implementing Redis Streams introduces zero new operational surface area. The team already understands Redis scaling, backup, and monitoring protocols, allowing us to focus 100% of our engineering effort on business-critical delivery features (e.g., retry policies and webhooks) rather than infrastructure management.

#### 2. Performance and Throughput at 10x Scale
Our 10x scale target demands handling a peak load of ~5,000 req/s. Since Redis is an in-memory database written in highly optimized C, a single Redis node can easily process over 100,000 read/write operations per second with sub-millisecond latency. 

While Apache Kafka offers massive, multi-partition throughput capable of handling millions of events per second, this level of throughput is highly over-engineered for our scale. Redis Streams provides more than enough headroom to handle our 10x target with a fraction of the hardware footprint and lower serialization/network overhead.

#### 3. Strict Ordering Guarantees
Redis Streams guarantees strict, append-only temporal ordering per stream via sequential, auto-incrementing message IDs (formatted as `timestamp-sequence`). This ensures that tasks updated, assigned, or completed events are processed in the exact order they occurred.

In Kafka, message ordering is only guaranteed *within a single partition*. To maintain sequence order across notification events, we would need to design a complex key-partitioning scheme. Any partition re-keying or scale-out repartitioning can cause out-of-order processing, adding unnecessary architectural risk to our notifications flow.

#### 4. Manageable Message Retention
Because Redis is RAM-bound, message retention is a critical factor. Redis Streams solves this natively by supporting stream trimming via the `MAXLEN` or `MINID` parameters (e.g., `XADD notifications_stream MAXLEN ~ 10000`). This allows us to keep our memory footprint bounded and predictable. Since notifications are transient events that are quickly processed, we do not require Kafka's persistent, disk-backed multi-gigabyte message retention logs. For historical auditing, we will write a backup record of sent notifications into our existing PostgreSQL database, keeping the hot path in Redis lean and fast.

#### 5. Native Consumer Groups
Redis Streams includes native consumer group features (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`) that mirror the core functional benefits of Kafka. 
- We can distribute notification events across multiple Python worker processes.
- The `XACK` command guarantees that messages are not lost if a consumer crashes mid-execution.
- The `XPENDING` and `XCLAIM` commands allow us to inspect stale or failed consumer jobs and safely re-assign them to healthy workers, providing a solid foundation for robust retries and Dead Letter Queues (DLQs).

In Kafka, partition rebalancing is managed automatically but can cause "stop-the-world" consumer pauses, which are highly disruptive when workers are blocked on slow third-party email or webhook network requests. Redis Streams consumer groups do not suffer from rebalance pauses, allowing for more predictable execution in synchronous Python worker threads.

#### 6. Exactly-Once Semantics (EOS) for Billing
While Kafka provides native "exactly-once" transactions internally, this guarantee **cannot** extend across external network boundaries (such as executing webhooks or calling Stripe/SendGrid APIs). Because third-party API calls cannot be rolled back, application-level deduplication is mandatory under both architectures.

To guarantee exactly-once delivery for billing-critical events, we will implement the **Transactional Outbox Pattern** within our PostgreSQL database:
1. When a billing event occurs, a record is written to a `billing_events` outbox table and committed in the same SQL transaction as the state change.
2. An asynchronous worker polls this table or listens to PostgreSQL `LISTEN/NOTIFY`, publishes the payload to Redis Streams, and processes it.
3. The notification consumer records the unique event ID in an idempotency table inside a PostgreSQL transaction before calling the third-party API.

Because application-level idempotency is required regardless of the broker, Kafka's complex internal EOS offers no practical advantage for our billing flow. Redis Streams' guaranteed *at-least-once* delivery (via explicit `XACK` checks) paired with PostgreSQL transactions is fully sufficient to achieve reliable, exactly-once business semantics.

#### 7. Time-to-Value and Developer Velocity
With standard Python client libraries (`redis-py`), configuring and connecting a Flask application to a Redis Stream takes less than 100 lines of code. This simplicity ensures that the new system can be developed, integrated with our monolith, fully tested, and shipped to staging within 3 to 5 days, well under our 2-week limit. 

Rolling out Kafka would require learning a new paradigm, selecting and configuring complex client libraries (such as `confluent-kafka` or `aiokafka`), establishing secure VPC networking, and validating complex cluster failure modes—a process that would easily consume 4 to 6 weeks.

---

## Consequences

### Positive (Pros):
* **Accelerated Time-to-Value**: We can ship a functional async notifications pipeline to production within our 2-week timeline.
* **Minimal Infrastructure Costs**: Utilizes existing Redis instances with zero additional SaaS licensing or complex AWS infrastructure costs.
* **Low Cognitive Overhead**: No new infrastructure paradigms or operational languages to master; 6-person team remains focused on product velocity.
* **Predictable Consumer Control**: Using `XCLAIM` allows the application to control retry intervals and backoffs explicitly without the risk of "stop-the-world" consumer rebalances.
* **WebSocket-Ready**: Leveraging Redis pub/sub alongside Streams creates a natural, low-latency integration point for real-time WebSocket pushing next quarter.

### Negative (Cons):
* **Memory Bound Storage (RAM Constraints)**: Unlike Kafka's disk-backed storage, Redis Streams store messages directly in RAM. A large backlog of unacknowledged or slow-processed messages could exhaust system memory. 
  * *Mitigation*: We will strictly cap stream lengths using `MAXLEN ~ 10000` (or `MINID`) during `XADD` operations and archive completed notifications to long-term cold storage in PostgreSQL for audit purposes.
* **Durability Trade-off**: If the Redis primary node suffers a hard crash before dirty data is persisted to disk or replicated, a small window of messages could be lost.
  * *Mitigation*: We will configure Redis persistence with Append-Only File (AOF) set to `appendfsync everysec`. Additionally, critical events (such as billing notifications) will be backed up in PostgreSQL first via the Outbox Pattern, ensuring they can be re-queued in a disaster recovery scenario.
* **Custom Backoff and DLQ Code**: Redis Streams does not provide out-of-the-box exponential backoff or DLQ forwarding.
  * *Mitigation*: We must implement a lightweight wrapper in Python that tracks message delivery attempts using the `XPENDING` idle time or a payload counter, and manually routing failed messages to a dedicated DLQ stream after $N$ unsuccessful attempts.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for this subsystem despite its outstanding technical features.

* **Why Rejected**:
  * **Operational Overhead**: The lack of a dedicated infrastructure engineer makes self-managing a 3-broker HA Kafka cluster (with KRaft or Zookeeper coordination) an unacceptable operational liability.
  * **Timeline Violations**: The learning curve, deployment configuration, networking setups, and integration tests would take at least a month, rendering the 2-week delivery constraint impossible to meet.
  * **Financial Inefficiency**: Enterprise managed services (like Confluent Cloud) are too expensive for our current stage, and the resource footprint of running our own HA Kafka brokers exceeds our modest budget.
  * **Diminishing Returns**: Kafka's unmatched capabilities (e.g., TB-scale disk retention, infinite message replayability, stream processing joins) are highly over-engineered for sending transient emails and webhooks. Its native Exactly-Once Semantics (EOS) are confined to the Kafka boundary and cannot solve the core challenge of idempotent integration with third-party external APIs.
