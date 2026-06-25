# ADR-001 — Notification Architecture

**Status:** Proposed

## Context

Our SaaS project management platform handles ~2M tasks per month across 85K monthly active users, with HTTP peaks of ~500 req/s. Notifications (emails, webhooks) are currently processed synchronously inside the Flask request cycle. This causes average response latencies of 800ms, spikes to 8s, silent drops on downstream failures, and cascading outages when slow webhook endpoints exhaust connection pools. We need to decouple notification delivery from HTTP requests, add retry with exponential backoff, and guarantee at-least-once delivery for all events and exactly-once semantics for billing-critical notifications (e.g., "trial expired", "payment failed"). Within two quarters we must also add real-time WebSocket push.

Our constraints are tight: a six-person engineering team (three senior, three mid-level) with no dedicated infrastructure engineer; a modest budget that rules out managed Confluent Cloud at scale; and a hard deadline of two weeks to deliver value from any new system. We already operate Redis in production for sessions and rate limiting. No one on the team has production Kafka experience.

## Decision

We will adopt **Redis Streams** as the backbone of the notification subsystem.

Redis Streams satisfies our throughput requirements (a single Redis node can sustain >100K messages/sec, far above our 500 req/s peak and 10× growth target) without introducing new infrastructure. Because Redis is already production-hardened for session storage and rate limiting, the team’s existing operational runbooks, monitoring, and backup procedures apply immediately. This keeps setup and migration inside the two-week window.

For exactly-once delivery of billing notifications, we will implement **idempotent consumers** using PostgreSQL: each billing event carries a unique idempotency key; consumers insert this key into a deduplication table within the same database transaction that processes the notification. Redis Streams provides at-least-once delivery with consumer-group-level acknowledgements (XACK); the idempotency layer upgrades the guarantee to exactly-once for the billing-critical path without requiring complex distributed transactions.

## Consequences

### Positive

- **Operational continuity**: The team already runs Redis. There is no new runtime to learn, monitor, or patch, and existing Redis replication gives us failover coverage on day one.
- **Speed to value**: We can deploy streams on the existing Redis infrastructure and begin migrating notification producers within days, well inside the two-week constraint.
- **Unified data plane**: Redis Streams for reliable queuing and Redis Pub/Sub for real-time WebSocket push can coexist on the same cluster, reducing the infrastructure footprint for the upcoming WebSocket milestone.
- **Sufficient headroom**: At 500 req/s peak (and even 5K req/s at 10× growth), Redis Streams is not the bottleneck. Memory, not throughput, becomes the binding constraint.

### Negative

- **Memory-bound retention**: Redis Streams stores data in memory (with optional AOF/RDB persistence). Retention must be managed explicitly via `XTRIM` or `MAXLEN`. If trimming is misconfigured, memory pressure can affect session storage and rate limiting (noisy-neighbor risk). We mitigate this by setting conservative stream caps and monitoring memory usage.
- **Application-level exactly-once**: Unlike Apache Kafka’s idempotent producer and transactional semantics, Redis Streams does not provide broker-level exactly-once delivery. Billing notifications rely on our idempotency-table guardrail, which adds a PostgreSQL write to the consumer hot path.
- **Horizontal scaling ceiling**: While Redis Cluster shards Streams, rebalancing stream consumers across cluster nodes is less mature than Kafka partition rebalancing. If we eventually outgrow Redis Cluster’s throughput or need indefinite log retention, we will need to migrate to a dedicated event-streaming platform.
- **Weaker replay ergonomics**: Redis Streams supports range queries (`XRANGE`), but it lacks Kafka’s rich consumer-offset management and log compaction. Replaying historical notifications for debugging or back-filling is more manual.

## Alternatives Considered

### Apache Kafka

Kafka was rejected because its operational complexity exceeds our team’s current capacity. A production Kafka deployment requires a minimum of three brokers (for HA) plus ZooKeeper or KRaft quorum management, partition rebalancing tuning, and consumer group coordinator monitoring. Our team has zero production experience with these components, and without budget for managed Confluent Cloud, we would bear the full operational burden ourselves. Estimates from comparable team profiles suggest a minimal production setup takes four to six weeks—not the two weeks available.

Kafka’s technical strengths—true exactly-once semantics via idempotent producers and transactions, disk-based retention with indefinite replay, and mature consumer-group rebalance protocols—are genuine, but they become decisive only at higher scale or when dedicated infrastructure expertise is available. We would revisit Kafka if notification volume crosses into sustained tens of thousands of events per second with complex stream-processing requirements, or if we hire dedicated platform engineering capacity.
