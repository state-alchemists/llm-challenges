# ADR-001: Notification Architecture — Redis Streams

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users, creating ~2M tasks per month with a peak load of ~500 req/s. Notifications (emails and webhooks) are currently handled synchronously inside the HTTP request cycle, causing:

- **Request timeouts**: average latency 800ms, spiking to 8s during peak hours
- **Silent failures**: dropped notifications with no retry or dead-letter queue
- **Cascading failures**: slow webhook endpoints exhausting connection pools and taking down unrelated features
- **No delivery guarantees**: billing-critical notifications (trial expired, payment failed) lack exactly-once semantics

We must decouple notification processing from HTTP requests, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), and lay groundwork for real-time WebSocket push notifications within two quarters. The solution must support 10x traffic growth (~5,000 req/s peak) without re-architecting.

**Constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already runs in production for sessions and rate limiting
- No Kafka experience on the team
- Setup and migration must deliver value within two weeks
- Budget is modest; managed Kafka (Confluent Cloud) is not viable at scale today

## Decision

**We will use Redis Streams as the messaging backbone for the notification subsystem.**

Redis Streams meets our throughput requirements, fits our operational constraints, and provides a viable path to the delivery guarantees we need without introducing unmanageable infrastructure complexity.

### Technical Justification

**Throughput:** Redis Streams handles ~100,000 messages/sec per node. Our current peak is ~500 req/s; even at 10x growth (~5,000 req/s) with multiple notification types per request, Redis Streams has ample headroom. Kafka’s million-messages-per-second throughput is compelling but unnecessary for our scale and timeline.

**Ordering Guarantees:** Redis Streams maintains strict FIFO ordering within a single stream. We will use separate streams per notification priority (e.g., `notifications:billing`, `notifications:general`, `notifications:webhooks`) to preserve ordering for related events while isolating slow consumers. This matches our need to process billing events in sequence without a general-purpose partitioning scheme.

**Message Retention:** Streams use memory-bound retention (`MAXLEN` or `MINID`). At our volume, retaining the last 24–48 hours of events consumes modest RAM; for longer durability, we will archive processed billing events to PostgreSQL. Kafka’s disk-based retention is superior for multi-day replay, but our consumers process notifications in near-real-time, so long retention is not a core requirement.

**Consumer Groups:** Redis Streams consumer groups provide auto-failover, horizontal scaling across multiple Python worker processes, and per-message acknowledgments. If a worker crashes, unacknowledged messages are re-delivered to another consumer in the group, satisfying our at-least-once requirement for general notifications.

**Exactly-Once Semantics for Billing:** Redis Streams does not offer Kafka-style idempotent producers or transactions. We will implement application-level exactly-once semantics for billing notifications using:
1. **Idempotent consumers**: each billing event carries a deterministic UUID; workers write the UUID to a Redis SET with a TTL before processing.
2. **Ack-after-commit**: the consumer ACKs the stream entry only after the email/webhook provider returns success and the idempotency key is persisted.
3. **Reconciliation**: a nightly job compares the billing event stream against the PostgreSQL outbox to catch any edge-case duplicates.

This adds application complexity, but it is bounded to one high-value workflow and avoids the operational burden of a full Kafka deployment.

**Operational Complexity:** Redis is already a production dependency. Adding Streams requires only a version check (Redis ≥ 5.0) and tuning `maxmemory-policy` to `noeviction` or `allkeys-lru` for the stream instances. The team does not need to learn ZooKeeper/KRaft, partition rebalancing, or broker tuning. Monitoring, alerting, and backup strategies reuse existing Redis runbooks.

**Real-Time WebSocket Path:** Redis pub/sub can power the WebSocket push layer in the same infrastructure, giving us a unified real-time stack. Kafka would require a separate bridge (e.g., Kafka → Redis/WebSocket) for sub-second push delivery.

**Setup Timeline:** Enabling Redis Streams on a dedicated Redis instance (or our existing cluster with logical isolation) and deploying Python consumers can be done in days, well within the two-week constraint. A production-ready self-hosted Kafka cluster—with KRaft, replication, partition planning, and consumer rebalancing tuning—would exceed that window for a team with no prior experience.

## Consequences

### Pros

- **Low operational overhead**: leverages existing Redis expertise, monitoring, and infrastructure; no new cluster technology to own.
- **Rapid time-to-value**: can ship async billing and general notifications within two weeks.
- **Sufficient throughput for 10x growth**: 5,000 req/s peak is comfortably within Redis Streams capacity.
- **Unified real-time stack**: pub/sub + streams in one system simplifies the WebSocket notification roadmap.
- **Cost-effective**: runs on existing modest AWS infrastructure; no managed service fees.
- **Strong per-stream FIFO ordering**: guarantees sequential processing of billing events without cross-partition complexity.

### Cons

- **Exactly-once is application-managed**: requires careful idempotency logic and reconciliation for billing events; bugs in consumer code can produce duplicates.
- **Memory-bound retention**: long-term replay (beyond hours/days) is not practical; historical audit trails must live in PostgreSQL.
- **Single-node bottleneck**: while one Redis node handles our projected scale, extreme growth beyond 10x may eventually require sharding or migration to a purpose-built log system.
- **Smaller ecosystem**: fewer mature stream-processing frameworks and tools compared to Kafka; we will build more consumer scaffolding in Python.
- **Durability trade-off**: AOF/RDB persistence is good but not as robust as Kafka’s replicated append-only log; a catastrophic Redis failure could lose unacknowledged messages.

## Alternatives Considered

### Apache Kafka

Kafka was rejected as the primary choice for this phase.

Kafka offers superior technical properties in several dimensions: true exactly-once semantics via idempotent producers and transactions, disk-based retention for days or weeks, millions of messages per second throughput, and a mature ecosystem (Kafka Connect, Kafka Streams, ksqlDB). For a company with dedicated platform engineers and a multi-year horizon, Kafka is the architecturally cleaner choice.

However, for our team and timeline, Kafka’s operational complexity is a liability:

- **Operational burden**: a production self-hosted Kafka cluster (even KRaft-mode) requires expertise in broker tuning, partition rebalancing, replication factor management, and consumer group rebalancing under failure. We have no team member with Kafka operational experience and no dedicated infrastructure engineer to own it.
- **Setup timeline**: standing up a reliable, monitored, replicated Kafka cluster, wiring it into our Python Flask monolith, and tuning consumer groups would take significantly longer than two weeks before delivering production value.
- **Budget constraint**: managed Confluent Cloud is explicitly ruled out at full scale, so we must self-host.
- **Overkill for current scale**: Kafka’s throughput and retention advantages do not become decisive until we are orders of magnitude beyond 5,000 req/s.

**Verdict:** Kafka remains the logical future target if we outgrow Redis Streams, but it is the wrong tool for our current team size, budget, and two-week delivery constraint. We will re-evaluate Kafka when we have dedicated platform capacity and traffic justifies the operational investment.
