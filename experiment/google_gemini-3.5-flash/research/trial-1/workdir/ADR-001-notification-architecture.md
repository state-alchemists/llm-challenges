# ADR-001: Selecting Redis Streams for the Notification Subsystem Architecture

- **Status**: Accepted
- **Date**: 2026-07-29
- **Deciders**: Zaruba (Lead Architect) & Engineering Team
- **Context tags**: system-architecture, messaging, notifications, redis, kafka

## Context

We run a SaaS project management platform with 85,000 monthly active users (MAU) generating approximately 2 million tasks per month. During business hours, our web servers experience peak loads of ~500 requests per second (req/s). 

### Current Architecture
* **Backend**: Python/Flask monolith (~50k lines of code)
* **Database**: PostgreSQL (single primary, one read replica)
* **Infrastructure**: 4 web servers behind an nginx load balancer on AWS
* **Cache**: Redis (currently utilized exclusively for session storage and rate limiting)
* **Notifications**: Handled synchronously inside the HTTP request cycle

### The Problem
Sending emails and webhooks synchronously when tasks are updated, assigned, or completed has introduced severe bottlenecks as usage scaled:
1. **Request Timeouts**: Sending notifications blocks the client response. Average request latency is 800ms, spiking to 8s during peak hours.
2. **Silent Failures**: Downstream failures of email providers or customer webhooks lead to silently dropped notifications with no automatic retries or Dead-Letter Queues (DLQs).
3. **Cascading Failures**: Connection pool exhaustion in the PostgreSQL database occurred twice this year because slow webhook endpoints blocked worker threads inside the monolith, cascading into a site-wide outage.
4. **No Delivery Guarantees**: Critical billing-related notifications (e.g., "trial expired", "payment failed") are delivered without transactional guarantees, which is unacceptable for billing operations.

### Scaling and Engineering Constraints
* **Decoupling**: Move notification delivery entirely out of the HTTP request cycle into asynchronous background workers.
* **Resilience**: Implement reliable message delivery with retries, exponential backoff, and a dead-letter mechanism.
* **Guarantees**: Ensure at-least-once delivery for general notifications, and exactly-once processing for billing-critical events.
* **Scaling Target**: Handle 10x current peak traffic growth (~5,000 req/s) without needing to re-architect.
* **Future Expansion**: Support real-time WebSocket push notifications within two quarters.
* **Team Size**: A small team of 6 engineers (3 senior, 3 mid-level) with *no dedicated infrastructure/operations engineer*.
* **Time-to-Value**: Setup, migration, and delivery of initial value must be achieved in **under 2 weeks**.
* **Experience**: The team already runs Redis in production but has zero operational experience with Apache Kafka.
* **Budget**: Modest infrastructure budget; managed Kafka solutions like Confluent Cloud are financially unfeasible at our target scale.

---

## Decision

We will use **Redis Streams** as the backbone of our asynchronous notification subsystem, coupled with our existing **PostgreSQL** database to achieve exactly-once processing for billing-critical notifications.

### Rationale

This decision is driven by a realistic assessment of our engineering constraints, operational capacity, budget, and performance needs:

1. **Zero Operational Overhead & Budget Fit**: We already run and monitor Redis in production for sessions and rate limiting. Reusing this instance (or scaling its AWS ElastiCache size slightly) adds zero new operational overhead and negligible financial cost. It avoids introducing a highly complex new stateful system into our architecture.
2. **Immediate Value Delivery (< 2 Weeks)**: Implementing a Redis Streams producer and consumer group in Python (using libraries like `redis-py` or lightweight wrappers) can be completed, tested, and deployed within a single week. This respects our strict 2-week time-to-value constraint.
3. **Sufficient and Scalable Throughput**: Redis Streams operates in-memory and can easily handle 100,000+ write operations per second on standard AWS instances. Our 10x target peak of 5,000 req/s represents only a small fraction of what a single Redis node can comfortably process.
4. **Built-in Consumer Groups and Backoff Support**: Redis Streams provides native consumer group abstractions (`XGROUP`, `XREADGROUP`, `XACK`). It automatically tracks unacknowledged messages via a Pending Entries List (PEL). This allows worker nodes to reclaim crashed jobs (`XCLAIM`) and facilitates building robust exponential backoff retries and Dead-Letter Queues (DLQs) in application code.
5. **Pragmatic Exactly-Once Semantics (EOS)**: 
   While Kafka offers native transactions, they only guarantee exactly-once processing *within* the Kafka loop. Because our workers send notifications to third-party APIs (e.g., SendGrid or external webhook targets), network errors during delivery can still cause duplicate sends. True exactly-once delivery across the network is physically impossible due to the Two Generals' Problem. 
   Therefore, exactly-once semantics must be enforced at the **application/database layer** regardless of the broker. We will leverage our existing PostgreSQL database as a deduplication log (using a unique constraint on `notification_id` and transactional `INSERT ... ON CONFLICT DO NOTHING` statements) alongside Redis-based distributed locks (`Redlock`) where necessary. This guarantees that billing-critical events are processed exactly once.

---

## Consequences

### Positive (Pros)
* **Rapid Time-to-Market**: We can leverage existing team knowledge and tooling to deploy the solution within the 2-week window.
* **Minimal Infrastructure Costs**: Reusing our existing Redis infrastructure eliminates the need for expensive new software licenses or dedicated cloud instances.
* **Simple Operational Model**: Our 6-person team does not need to learn, configure, secure, monitor, or patch a complex distributed streaming system.
* **Horizontal Scaling of Workers**: Multiple background consumer processes across our 4 existing servers (or new dedicated worker nodes) can join a Redis Streams Consumer Group, processing notifications concurrently and safely.
* **Low Latency**: Processing occurs entirely in-memory, resulting in sub-millisecond publishing latency.

### Negative (Cons)
* **Memory Limits (Retention)**: Because Redis is an in-memory database, keeping a long-term historical log of processed notifications is not viable. We must actively cap our streams using `XADD ... MAXLEN ~ 10000` to prevent memory exhaustion.
* **Durability Trade-off**: By default, Redis is configured with `appendfsync everysec` for AOF persistence. In the event of a catastrophic host crash, up to 1 second of published notifications could be lost. We will mitigate this by writing a lightweight backup log of critical billing notifications to PostgreSQL *before* publishing to Redis Streams, utilizing PostgreSQL's ACID transaction log for permanent durability.
* **No Native Replayability**: Unlike Kafka, which supports replaying consumer groups from arbitrary offsets days in the past, Redis Streams are designed as active buffers. Once messages are acknowledged and pruned, they cannot be replayed.

### Follow-up Actions
1. **Dynamic Stream Capping**: Configure all worker tasks to publish to capped streams using the `MAXLEN ~ <size>` modifier.
2. **Deduplication Ledger**: Implement a `processed_notifications` table in PostgreSQL with a unique constraint on `(notification_id, event_type)` to act as the idempotency guard for billing-critical events.
3. **PEL Monitor Daemon**: Write a lightweight monitoring worker that queries the Stream Pending Entries List via `XPENDING` to automatically retry or escalate messages that have remained unacknowledged for more than 5 minutes.
4. **DLQ Storage**: Implement a persistent Dead-Letter Queue in PostgreSQL for notifications that have failed all exponential backoff retries, ensuring no alerts are lost.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Apache Kafka is a world-class, disk-backed distributed event streaming platform, but it is fundamentally mismatched with our current constraints and team composition.

* **Why Rejected**:
  1. **Prohibitive Operational Complexity**: Running Kafka requires configuring, monitoring, and managing a cluster of Kafka brokers along with a coordinator (KRaft or Zookeeper). For a 6-person team with no dedicated infrastructure engineer, self-hosting Kafka in production is an immense operational risk that would distract from product delivery.
  2. **Severe Timeline Violation**: The steep learning curve, infrastructure setup, network configuration, client integration, and disaster-recovery testing would take at least 3-4 weeks—violating our 2-week deadline.
  3. **High Financial Cost**: We cannot afford Confluent Cloud's managed pricing tier at our target scale under our modest budget, and self-managed multi-node EC2 clusters would incur substantial compute, EBS disk, and inter-AZ data transfer costs.
  4. **Over-engineering for Scale**: Kafka is built to handle millions of events per second across hundreds of partitions. Our projected 10x peak load of 5,000 req/s is easily handled by Redis, making Kafka's operational burden unnecessary.
  5. **Ephemeral Storage Misalignment**: Notifications are transient events. Once sent, we do not need Kafka’s persistent storage, log compaction, or long-term multi-day message replay capabilities.
* **What Would Have Made It Win**: We would have chosen Apache Kafka only if our team had a dedicated platform/operations engineer, a significantly larger infrastructure budget to afford Confluent Cloud, a timeline of >2 months, and a required throughput exceeding 50,000 req/s with strict requirements for multi-day message replayability across multiple distinct down-stream consumer systems.
