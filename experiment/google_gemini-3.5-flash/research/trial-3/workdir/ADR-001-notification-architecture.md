# ADR-001: Notification Architecture Selection

- **Status**: Proposed
- **Date**: 2026-06-23
- **Deciders**: Engineering Team (3 senior, 3 mid-level)
- **Context tags**: notification, architecture, event-streaming, messaging

## Context

The current system is a Python/Flask monolith running synchronous notification delivery (emails and webhooks) directly inside the HTTP request cycle (`system_context.md:11,15`). This synchronous pattern blocks user responses, resulting in an average response latency of 800ms, spiking to 8s during peak traffic hours of ~500 req/s (`system_context.md:8,19`). This has caused:
1. **Request timeouts**: Severe performance degradation during peak hours (`system_context.md:19`).
2. **Silent failures**: Notifications are dropped without retries or dead-letter queues (DLQ) if third-party email or webhook services are offline (`system_context.md:20`).
3. **Cascading failures**: Two production outages were triggered this year due to connection pool exhaustion from slow downstream webhook targets, impacting unrelated features (`system_context.md:21`).
4. **No delivery guarantees**: Billing-critical events (e.g., "trial expired", "payment failed") have no transactional safety and are prone to double-delivery or silent drops (`system_context.md:22`).

To support a 10x traffic growth target (scaling to ~5,000 req/s and ~20M tasks/month) without re-architecting, the system must decouple notification processing into an asynchronous pipeline (`system_context.md:26,30`). This pipeline must support:
- Reliable async message ingestion and processing (`system_context.md:26`).
- Message retries with exponential backoff and DLQ capabilities (`system_context.md:27`).
- At-least-once delivery guarantees for all notifications, and exactly-once processing (semantics) for billing notifications (`system_context.md:28,38`).
- Extremely low latency to power real-time WebSocket push notifications scheduled for delivery within two quarters (`system_context.md:29`).

The engineering team operates under strict constraints:
- **Personnel**: 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure/devops engineer** (`system_context.md:33`).
- **Knowledge**: No Kafka experience on the team (`system_context.md:35`).
- **Timeline**: Must deliver value and go live in **less than 2 weeks** (`system_context.md:36`).
- **Budget**: Modest budget; managed Kafka solutions like Confluent Cloud are cost-prohibitive at our planned scale (`system_context.md:37`).
- **Existing Tech**: Redis is already successfully deployed and operated in production for session storage and rate limiting (`system_context.md:14,34`).

## Decision

We will use **Redis Streams** as the core messaging and event-streaming subsystem for the notifications pipeline. 

### Justification

Redis Streams provides a lightweight, highly performant, and transactionally reliable event-streaming model that fits perfectly within our 2-week implementation timeline and modest operational budget.

1. **Zero Operational Overhead (Constraints Match)**:
   We already run, configure, and monitor Redis in production for session storage and rate limiting (`system_context.md:14,34`). Using Redis Streams avoids introducing a new database, cluster, or complex piece of infrastructure. This allows our small team of 6 engineers to deliver business value within the 2-week target without needing a dedicated infrastructure engineer (`system_context.md:33,36`).

2. **Perfect Fit for Exactly-Once Semantics (EOS)**:
   In distributed notification pipelines (sending emails or webhooks over public networks), exactly-once *delivery* is physically impossible due to the network-level Two Generals' Problem. Therefore, exactly-once semantics must be achieved via **at-least-once delivery** combined with **idempotency at the consumer level**.
   - Redis Streams provides robust at-least-once guarantees via consumer groups, tracking unacknowledged messages in the Pending Entries List (PEL) via `XPENDING` and claiming them with `XCLAIM`/`XAUTOCLAIM`.
   - Consumer-level idempotency requires a high-performance key-value store to track processed transaction IDs/idempotency keys with a Time-To-Live (TTL). Redis is already the industry standard for this store.
   - By choosing Redis Streams, the consumer can run its message consumption AND idempotency check (`SET key value NX PX`) against the exact same database. This reduces network hops to zero (or low single-digit milliseconds), dramatically simplifies consumer transaction logic, and avoids the architectural complexity of bridging a broker (Kafka) with a separate state store (Redis).

3. **Sub-Millisecond Latency for WebSockets**:
   Redis Streams operates purely in-memory, delivering sub-millisecond end-to-end processing latencies. This is ideal for our upcoming real-time WebSocket push notifications requirement (`system_context.md:29`), where message dispatch lag must be imperceptible.

4. **10x Scale Headroom**:
   While Apache Kafka is designed for gigabytes-per-second throughput, Redis Streams easily processes over 100,000 write operations per second on a single thread. Our 10x peak traffic target of ~5,000 req/s (`system_context.md:8,30`) represents less than 5% of a modest Redis instance's capacity, ensuring massive scaling headroom without any re-architecture.

## Consequences

### Pros (Positive)
* **Immediate Developer Velocity**: The team can use existing Python clients (`redis-py`) and their deep familiarity with Redis to build, test, and deploy the entire async notifications pipeline within the 2-week deadline (`system_context.md:34,36`).
* **Minimal Infrastructure Costs**: Leverages our existing AWS hosted Redis deployment, incurring zero additional infrastructure licensing or subscription fees (`system_context.md:13,34`).
* **Unified State and Streaming**: Simplifying our technology stack by using Redis as the event broker, rate limiter, session storage, and idempotency store.
* **Low Latency**: In-memory architecture ensures sub-millisecond streaming latency, providing an optimal foundation for the real-time WebSocket push features (`system_context.md:29`).
* **Robust Consumer Recovery**: Built-in Consumer Groups, PELs, and acknowledgement tracking (`XACK`) ensure no messages are lost if a worker crashes during processing.

### Cons (Negative)
* **In-Memory Storage Cost**: Redis keeps all active stream messages in-memory. If consumers stall or stop processing, memory consumption will increase linearly. We must mitigate this by sizing our instances appropriately and setting strict message pruning policies (e.g., using `MAXLEN ~ 100000` or `MINID` during `XADD` to trim processed/old elements).
* **No Out-of-the-Box Persistence Mirroring**: Unlike Kafka's disk-first architecture, Redis relies on AOF (Append-Only File) and RDB snapshotting for persistence. In a catastrophic primary crash, a small window of un-replicated stream messages could be lost. We must configure `appendfsync everysec` to bound maximum loss to a single second of transactions, which is acceptable for notification workloads.
* **Lack of Ecosystem Connectors**: Kafka has a rich connector ecosystem (Kafka Connect). With Redis Streams, we must write custom Python consumer logic to handle retries, backoffs, and dead-letter routing manually.

## Alternatives Considered

### Apache Kafka

Apache Kafka was evaluated but rejected due to extreme operational, knowledge, and budget barriers:

* **Operational Complexity & Team Constraint**: Kafka is notoriously complex to deploy, configure, secure, and monitor. It requires managing JVM memory, garbage collection, partition sizing, and coordination services (KRaft or Zookeeper). Operating a Kafka cluster reliably in production without a dedicated platform/infrastructure engineer (`system_context.md:33`) presents unacceptable risk.
* **Timeline Failure**: Acquiring the necessary expertise, building stable Infrastructure-as-Code for multi-AZ brokers, and implementing reliable Python consumers (`confluent-kafka` or `kafka-python`) would easily exceed the 2-week deadline for a team with zero prior Kafka experience (`system_context.md:35,36`).
* **Excessive Financial Cost**: Self-hosting Kafka securely on AWS requires a minimum of 3 broker instances and multi-AZ replica configurations, leading to high infrastructure overhead. Managed alternatives like Confluent Cloud are cost-prohibitive given our modest budget constraints (`system_context.md:37`).
* **Over-Engineering**: Kafka's architecture is optimized for massive throughput (millions of events/sec) and cold disk storage. Our peak 10x growth target (~5,000 req/s) is trivial for Redis Streams (`system_context.md:8,30`), making Kafka an expensive, unnecessary over-complication for our scale.
