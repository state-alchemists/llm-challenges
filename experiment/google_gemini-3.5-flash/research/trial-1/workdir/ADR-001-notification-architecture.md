# ADR-001: Choice of Notification Subsystem Messaging Infrastructure

## Status
Proposed

## Context

### Background
We operate a SaaS project management platform serving 85,000 monthly active users (MAU) and generating approximately 2 million tasks per month. During peak business hours, the system handles about 500 requests per second (req/s). 

### The Problem
Currently, the system handles notifications (emails and webhooks) synchronously within the HTTP request cycle. This architecture introduces severe operational hazards:
1. **Request Timeouts**: Sending notifications blocks the HTTP response, resulting in an average latency of 800ms, which spikes to over 8 seconds during peak hours.
2. **Silent Failures**: Network glitches or downtime from external email providers and webhook endpoints result in silently dropped notifications. The system lacks retry mechanisms or a Dead Letter Queue (DLQ).
3. **Cascading Failures**: Connection pools have been exhausted twice this year due to slow third-party webhook endpoints, resulting in platform-wide outages of unrelated features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as subscription expirations and payment failures) have no delivery guarantees, risking revenue and user churn.

### Scaling Target
To address these issues, we must transition to an asynchronous notification subsystem that meets the following criteria:
- **Decoupled Async Processing**: Isolate notification execution from the user-facing request cycle.
- **Robust Retry Logic**: Support retry policies with exponential backoff and jitter.
- **Delivery Guarantees**: Guarantee at-least-once delivery for billing events and exactly-once processing where feasible.
- **Real-Time Delivery**: Support real-time WebSocket push notifications to be introduced within two quarters.
- **10x Scalability**: Scale throughput capacity to support 5,000 req/s (10x current peak) without requiring an architectural rewrite.

### Constraints
- **Team Size**: A small team of 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure or DevOps engineer.
- **Skillset**: The team has zero operational or development experience with Apache Kafka but possesses strong working experience with Redis.
- **Existing Infrastructure**: We currently run Redis in production for session storage and rate limiting.
- **Timeline**: The solution must be implemented, tested, and deployed to production in less than 2 weeks.
- **Budget**: Modest budget constraints rule out premium managed service offerings (such as Confluent Cloud at scale) for the foreseeable future.

---

## Decision

We will use **Redis Streams** as the messaging infrastructure for the notification subsystem.

### Justification

1. **Zero Infrastructure Overhead**: We already run, manage, and monitor Redis in our production environment. Choosing Redis Streams avoids introducing any new third-party software, clustering managers, or external infrastructure components. This perfectly aligns with our tight 2-week implementation constraint.
2. **Performance and 10x Scalability**: Redis runs in-memory and can easily handle our peak load of 500 req/s and our 10x target of 5,000 req/s with sub-millisecond latencies. It provides ample headroom without the need to manage a heavyweight distributed commit log.
3. **Reliable Consumer Groups**: Redis Streams native consumer groups (via `XGROUP`, `XREADGROUP`, and `XACK`) provide robust features for scaling consumers. It maintains a Pending Entries List (PEL) to track which messages were delivered but not yet acknowledged. This enables reliable message recovery, handling of worker crashes, and delivery retries without message loss.
4. **Straightforward WebSocket Integration**: Real-time push notifications can easily leverage Redis Streams or Redis Pub/Sub, simplifying the transition to WebSockets planned for next quarter.
5. **Pragmatic Exactly-Once Semantics**: To fulfill the requirement for exactly-once billing notifications, we will implement an **Idempotent Consumer** pattern. Since external systems (like email APIs or payment webhooks) do not support distributed transactions, a messaging system alone cannot guarantee exactly-once execution. By leveraging Redis Streams' at-least-once guarantees and matching them with a unique transaction ID/idempotency key verified within a PostgreSQL transaction on the consumer side, we achieve reliable, exactly-once processing with minimal complexity.

---

## Consequences

### Positive (Pros)
* **Operational Simplicity**: No new infrastructure. The operational footprint is identical to our current stack, eliminating the need for a dedicated infrastructure engineer.
* **Rapid Developer Onboarding**: Since developers already have Redis running locally for session storage, local development, testing, and debugging are immediate and simple.
* **Extremely Low Latency**: Redis's in-memory data structures provide significantly lower publish/subscribe latencies compared to disk-backed message brokers under standard operations.
* **Built-in Fault Tolerance**: Redis Streams' Pending Entries List (PEL) and active claiming (`XAUTOCLAIM`) allow safe processing retries, eliminating silent failures.

### Negative (Cons)
* **In-Memory Storage Constraint**: Redis stores streams in-memory. If consumers fall behind or fail, memory consumption will increase, risking Out-Of-Memory (OOM) errors.
  * *Mitigation*: We will configure deterministic stream trimming on every append using the `MAXLEN ~ N` parameter (e.g., maintaining a rolling log of the last 100,000 messages). Completed or failed messages exceeding retry limits will be archived to a PostgreSQL audit table.
* **Persistence Trade-Offs**: Unlike Kafka's disk-first write path, Redis persistence (RDB/AOF) can result in minor data loss (typically <1 second of writes) in the event of a sudden, catastrophic node failure depending on the sync configuration.
  * *Mitigation*: We will configure AOF (Append-Only File) with `appendfsync everysec` on our Redis instance. For highly critical billing events, the Flask monolith will first write the event to PostgreSQL (our transactional source of truth) before publishing to Redis, allowing recovery from our relational database if needed (Transactional Outbox pattern).

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the notification subsystem due to the following reasons:

1. **Extreme Operational Complexity**: Kafka requires ZooKeeper or KRaft to coordinate clusters. Managing a highly available production Kafka cluster requires deep expertise. Without a dedicated infrastructure engineer on a 6-person team, managing a self-hosted Kafka cluster is an unacceptable operational risk.
2. **Steep Learning Curve**: With zero Kafka experience on the team, we would fail to meet the 2-week implementation timeline. Designing, testing, and deploying Kafka-based consumers safely within this timeframe is not realistic.
3. **Budget Constraints**: Managed solutions like Confluent Cloud are cost-prohibitive at our target 10x scale given our modest budget constraints.
4. **Over-engineering**: Kafka is designed to process gigabytes of data per second and maintain persistent logs indefinitely. For a notification system scaling to 5,000 events per second, Kafka's capabilities are vastly over-engineered, while its administrative overhead remains high.
