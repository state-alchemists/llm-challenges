# ADR-001: Adopt Redis Streams for the Asynchronous Notification Subsystem

## Status

Proposed

## Context

The current notification module in our Python/Flask monolith sends emails and webhooks synchronously inside the HTTP request cycle. At peak load (~500 req/s), this produces average latencies of 800ms and spikes to 8s, causing request timeouts. Silent failures are common when downstream endpoints are unavailable, and two incidents this year involved slow webhook endpoints exhausting connection pools and cascading into unrelated features. Billing-critical notifications (e.g., "trial expired", "payment failed") currently have no delivery guarantee.

We must decouple notifications from the HTTP request cycle and move to an asynchronous, queue-backed architecture with the following requirements:

- **Throughput**: support current peak of ~500 req/s and 10x growth (~5,000 req/s) without re-architecting.
- **Ordering**: per-user or per-task ordering is sufficient; global total ordering is not required.
- **Message retention**: notifications are time-sensitive; a retention window of 24–72 hours covers retry and recovery needs.
- **Consumer groups**: multiple worker processes must share the load with automatic rebalancing.
- **Exactly-once semantics**: billing notifications must be delivered exactly once; other notifications can tolerate at-least-once delivery with idempotent retries.
- **Operational complexity**: the team has six engineers (three senior, three mid-level) and no dedicated infrastructure engineer. The solution must go to production within two weeks and run on a modest budget.

We already operate Redis in production (session storage and rate limiting). No team member has prior experience operating Apache Kafka.

## Decision

We will use **Redis Streams** as the message bus for the notification subsystem.

Redis Streams meets our throughput target (a single Redis instance can sustain tens of thousands of writes per second) and its consumer-group semantics provide the load balancing and partition-scoped ordering we need. Because Redis is already in production, we can ship within the two-week window by reusing existing infrastructure, monitoring, and operational playbooks. Exactly-once delivery for billing events will be enforced at the application layer using our existing PostgreSQL database to track processed message IDs transactionally, rather than relying on a platform-level guarantee.

## Consequences

### Positive

- **Low operational overhead**: Redis is already deployed, monitored, and backed up. Adding Streams does not introduce a new service or operational surface area.
- **Fast time-to-value**: Redis Streams is a data type, not a separate cluster. We can prototype and deploy in days, well under the two-week limit.
- **Sufficient throughput**: At our 10x target of ~5,000 messages per second, a single Redis node with AOF persistence is well within its performance envelope.
- **Consumer groups**: `XREADGROUP` with `>` semantics provides automatic partitioning of streams across worker processes and tracks per-consumer offsets in Redis itself.
- **Retention control**: `MAXLEN` or `XTRIM` on stream insertion gives us precise, time-bounded retention without unbounded memory growth.
- **Synergy with future WebSocket push**: Redis Pub/Sub (already available) is the natural backend for real-time WebSocket broadcasts in the next two quarters. Running both Streams (queue) and Pub/Sub (push) on the same Redis deployment simplifies the architecture.
- **Cost**: No additional infrastructure licensing or managed-service fees. We stay within our modest budget.

### Negative

- **Exactly-once is application-layer responsibility**: Redis Streams provides at-least-once delivery. Billing notifications require consumers to check a PostgreSQL deduplication table (message ID → processed timestamp) before acting and to commit the ACK only after the database insert succeeds. This adds application complexity and a small latency penalty for billing events.
- **Memory-bound retention**: Unlike Kafka's disk-based log segments, Redis Streams lives in memory (with optional persistence). If consumers fall behind beyond the retention window, messages are lost. We must set aggressive alerting on stream length and consumer lag.
- **Less mature ecosystem**: Redis Streams lacks the rich tooling (e.g., schema registry, Kafka Connect, stream processors like ksqlDB) that Kafka offers. We will build consumers as plain Python workers.
- **Durability model**: AOF rewrite failures or full-system crashes carry a small risk of losing the last few seconds of messages. For billing events, PostgreSQL deduplication covers this gap; for non-billing events, at-least-once retry compensates.

## Alternatives Considered

### Apache Kafka

Kafka was rejected because its operational complexity and setup time exceed our constraints.

- **Operational complexity**: A production Kafka deployment requires broker tuning, replication-factor configuration, partition planning, and monitoring of consumer-group rebalancing. With no infrastructure engineer and a six-person team, ongoing ownership would pull cycles from product engineering.
- **Setup time**: Building a reliable, self-hosted Kafka cluster (or even a single-node evaluation deployment with KRaft) and integrating it with our Python workers would take more than two weeks.
- **Cost**: Managed Kafka (Confluent Cloud, AWS MSK) was ruled out by budget constraints. Self-hosted Kafka requires dedicated compute resources, increasing AWS spend.
- **Exactly-once semantics**: Kafka provides native exactly-once semantics (idempotent producers + transactions + consumer isolation), which is technically superior for billing events. However, this advantage does not outweigh the delivery risk introduced by our team's lack of operational experience with Kafka.

Kafka would become the preferred choice if our throughput requirement exceeded what a single Redis node could provide (roughly >50,000 msg/s sustained), if we required multi-region replication, or if we had dedicated infrastructure staff to operate the cluster.
