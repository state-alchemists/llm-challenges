# ADR-001 — Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project-management platform handles 85,000 monthly active users and ~2 million task events per month, with HTTP peaks of ~500 req/s. Today, notifications (emails and webhooks) are dispatched synchronously inside the Flask request cycle. This has caused four concrete problems:

1. **Request timeouts** — average latency 800 ms, spiking to 8 s during peaks because the thread blocks on external SMTP and HTTP calls.
2. **Silent failures** — if an email provider or webhook endpoint errors, the notification is dropped with no retry or dead-letter mechanism.
3. **Cascading failures** — two incidents this year where a slow webhook exhausted the WSGI connection pool and degraded unrelated endpoints.
4. **Missing delivery guarantees** — billing-critical events (trial expired, payment failed) must be delivered exactly once, but the current code provides no idempotency or transaction boundary.

We must decouple notification production from the HTTP path, add retry with exponential backoff, and guarantee at-least-once delivery (exactly-once for billing events). Within two quarters we also intend to add real-time WebSocket push, and we need a path to 10× traffic growth (≈ 5,000 req/s peak) without re-architecting.

## Decision

We will adopt **Redis Streams** as the backbone of the notification subsystem.

This decision is driven by operational fit rather than raw throughput. Redis Streams satisfies our performance headroom — a single Redis node can sustain well over 100,000 messages/s, giving us 20× margin above the 5,000 req/s target — while keeping operational risk within what a six-person team can safely manage. Because we already run Redis for sessions and rate limiting, the same infrastructure expertise applies to monitoring, backup, and failover. No new binary, no new deployment topology, and no partition-rebalancing learning curve are required.

Exactly-once semantics for billing events will be implemented at the application layer using deterministic idempotency keys (composite of billing-event UUID and channel type) stored in a Redis-backed deduplication set with a 24-hour TTL. This pattern is sufficient because our consumers are idempotent by nature: re-processing the same billing notification with the same idempotency key is a no-op after the first successful external delivery.

## Consequences

### Positive

- **Fast time-to-value**: Redis Streams is available on the infrastructure we already run. A minimal producer/consumer pair can be deployed in days, fitting inside the two-week migration window.
- **Low operational overhead**: The team already knows Redis monitoring, persistence (AOF + RDB), and failover. Adding a Streams workload does not change the operational model.
- **Adequate throughput**: At 5,000 req/s peak we remain two orders of magnitude below single-node Redis Streams limits, so horizontal partitioning is unnecessary today.
- **Built-in consumer groups**: `XREADGROUP` and `XACK` give us competing consumers with automatic rebalancing, satisfying the requirement for multiple notification workers without external coordination.
- **WebSocket synergy**: Redis Pub/Sub (already available) can serve the real-time push layer in Q3, keeping the messaging stack uniform.

### Negative

- **At-least-once by default**: Redis Streams does not provide Kafka-style idempotent producers or transactional consume-process-produce loops. We must build and maintain the idempotency layer ourselves for billing events.
- **Memory-bound retention**: Streams are kept in RAM; large backlogs during an outage require explicit `MAXLEN` trimming or eviction policies. We commit to a retention policy of 72 hours for the primary stream and moving dead messages to a secondary list for offline analysis.
- **Weaker ordering across multiple stream keys**: If we later shard notifications by tenant or type, total ordering is lost. We accept this because notification events are independent and do not require cross-key ordering.
- **Revisit at 10×+ growth**: While Redis Streams handles 5,000 req/s comfortably, if we eventually exceed ~50,000 req/s or need complex stream processing (windowed aggregates, joins), we will need to re-evaluate and likely migrate to Kafka. This decision is therefore bounded to our current scaling horizon.

## Alternatives Considered

### Apache Kafka

Kafka was rejected because its operational complexity exceeds our team's capacity today.

- **Exactly-once semantics**: Kafka provides native idempotent producers and transactional APIs, which would eliminate the need for application-level deduplication. This is a genuine technical advantage.
- **Disk-based retention and replay**: Kafka's log-based storage supports indefinite retention and arbitrary consumer rewinds, which Redis Streams cannot match without external archival.
- **Operational barrier**: Self-hosting Kafka requires managing brokers, KRaft (or ZooKeeper) quorum, partition assignment, replication factors, and careful JVM tuning. Our team has zero prior experience and no dedicated infrastructure engineer. Running a production-grade Kafka cluster safely inside two weeks carries an unacceptable risk of misconfiguration-induced outages.
- **Cost barrier**: Managed options such as Confluent Cloud or AWS MSK are explicitly out of budget. A managed service would have removed the operational concern, but the constraint is binding.

We would have chosen Kafka if the budget allowed a managed offering or if the team included an infrastructure engineer with Kafka experience. Under current constraints — modest budget, no Kafka expertise, and a two-week delivery window — the operational risk of Kafka outweighs its technical benefits.
