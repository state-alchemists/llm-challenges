# ADR-001: Notification Architecture — Redis Streams

## Status

Proposed

## Context

Our SaaS project-management platform serves 85,000 monthly active users and creates roughly 2M tasks per month. During business hours we peak at ~500 req/s. Notifications (emails and webhooks) are still handled synchronously inside the Flask HTTP request cycle. This has produced four concrete failures:

1. **Request timeouts** — average notification latency is 800 ms and spikes to 8 s during peak hours, degrading the user experience for every mutating endpoint.
2. **Silent failures** — when an email provider or downstream webhook is unavailable the notification is dropped with no retry or dead-letter queue.
3. **Cascading failures** — two incidents this year where a slow webhook caused connection-pool exhaustion and took down unrelated features.
4. **No delivery guarantees** — billing-critical events (trial expired, payment failed) must be delivered exactly once, but the current code path offers no such mechanism.

We must move to an async, decoupled notification pipeline that supports retry with exponential backoff, at-least-once delivery for all events, and exactly-once semantics for billing notifications. Within two quarters we also want to add real-time WebSocket push. The target scale is 10× current traffic (~5,000 req/s peak).

Team and infrastructure constraints:

- Engineering team of six (three senior, three mid-level), **no dedicated infrastructure engineer**.
- We already run Redis in production for sessions and rate limiting.
- **No one on the team has operated Kafka before**.
- Migration must deliver value in **≤2 weeks**.
- Budget is modest; managed Confluent Cloud is not affordable at target scale.

## Decision

We will implement the new notification pipeline on **Redis Streams**.

The primary driver is risk-adjusted time-to-value. Redis Streams gives us the ordering guarantees, consumer-group semantics, and throughput headroom we need for the next 18–24 months, while letting the team leverage existing operational expertise and infrastructure. A self-hosted Kafka cluster, or even a minimal AWS MSK deployment, would introduce broker management, partition tuning, and consumer-rebalance complexity that we are not staffed to own inside a two-week migration window.

### Exactly-once semantics for billing events

Redis Streams does not provide server-side exactly-once delivery out of the box. We will achieve effectively-once processing with an **idempotent consumer pattern** backed by our existing PostgreSQL primary:

1. Every billing notification is published with a deterministic UUID (event-id derived from the billing entity and operation type).
2. Before executing the side effect (sending email, calling webhook), the consumer attempts to insert the event-id into a PostgreSQL `processed_events` table that has a unique constraint on `event_id`.
3. If the insert succeeds, the consumer proceeds and then acknowledges (XACK) the message in Redis.
4. If the insert violates the unique constraint, the consumer treats the event as already handled and XACKs it immediately.

This pattern keeps our exactly-once guarantee in the same transactional store we already operate, rather than adding a new distributed system to maintain.

## Consequences

### Pros

- **Operational continuity** — The team already monitors, backups, and patches Redis. Adding Streams uses the same runbooks, dashboards, and failover procedures.
- **Throughput headroom** — A single Redis node can sustain >100,000 messages/sec with Streams. Our 10× target of ~5,000 req/s leaves two orders of magnitude of headroom without horizontal partitioning.
- **Ordering guarantees** — Messages inside a single stream are strictly ordered. We can separate streams by notification type (e.g., `stream:billing`, `stream:webhooks`, `stream:emails`) so that ordering is preserved per domain without head-of-line blocking across domains.
- **Consumer groups** — Redis Streams consumer groups (`XREADGROUP`, `XACK`, `XPENDING`) give us competing-consumer scaling, automatic message claiming for failed consumers, and observability into lag per consumer.
- **Two-week feasibility** — We can reuse the existing Redis instance, add a small Python worker service (Celery or a lightweight `redis-py` consumer), and migrate endpoints incrementally. No new infrastructure procurement is required.
- **WebSocket synergy** — Redis Pub/Sub (already available) can power the real-time WebSocket layer in Q3–Q4, reusing the same Redis cluster and reducing future infrastructure sprawl.
- **Cost** — Near-zero marginal cost because we already pay for the Redis instance.

### Cons

- **Memory-bound retention** — Redis is an in-memory store. Very long retention or large backlogs during an outage will consume RAM. We will mitigate this with: (a) short TTLs on non-critical notification streams (24–48 h), (b) immediate archival of billing events to PostgreSQL after processing, and (c) memory alerts that trigger consumer scaling before the node fills.
- **No native exactly-once** — The idempotent-consumer pattern adds one extra write (and one read under contention) per billing event. If PostgreSQL is unavailable, billing consumers must pause rather than proceed, creating a small availability coupling. We accept this trade-off because billing events already depend on PostgreSQL for state.
- **Single-node risk (today)** — Our current Redis is a single instance. For the notification pipeline we should add a Redis replica and configure Sentinel or move to ElastiCache Replication for automatic failover; this is modest extra work but must be tracked.
- **Ecosystem maturity** — Kafka has richer surrounding tooling (Kafka Connect, Kafka Streams, Schema Registry). We do not need these today, but if we later need complex stream processing we may outgrow Redis Streams and revisit this decision.

## Alternatives Considered

### Apache Kafka

Kafka was evaluated seriously because it is the industry-standard reference for durable, high-throughput event streaming.

**Why it was rejected:**

- **Operational burden** — Self-hosting Kafka means managing brokers, ZooKeeper (or KRaft), partition replication, ISR management, and consumer-group rebalancing. With no dedicated infrastructure engineer, the team would be learning and operating a complex distributed system under a two-week deadline.
- **Cost at scale** — AWS MSK or Confluent Cloud would eliminate operational burden but exceeds our modest budget at 10× traffic. A self-hosted EC2 cluster is cheaper but magnifies the operational risk.
- **Exactly-once complexity** — Kafka’s exactly-once semantics (idempotent producer + transactions + `read_committed` consumers) are powerful but notoriously difficult to configure and debug. A misconfigured transaction timeout or unclean leader election can silently break the guarantee we are trying to establish.
- **Overkill for present scale** — Kafka shines at millions of messages per second and cross-datacenter replication. Our 10× target (~5,000 req/s) is well inside the comfortable operating envelope of a single Redis node.

Kafka remains the logical next step if we ever need geo-replicated streams, complex stream processing, or sustained throughput beyond what Redis can provide on a single node. We will re-evaluate when we cross that threshold.
