# ADR 001 — Notification subsystem message broker

- **Status**: Proposed
- **Date**: 2026-06-23
- **Deciders**: Engineering team (3 senior, 3 mid-level)
- **Context tags**: notifications, architecture, scaling, redis, kafka

## Context

Our notification module sends emails and webhooks synchronously inside the HTTP request cycle. This causes request timeouts (average 800 ms, spiking to 8 s at peak), silent failures with no retry or dead-letter queue, and cascading failures — two incidents this year where slow webhook endpoints exhausted the connection pool and took down unrelated features. Billing-critical notifications ("trial expired", "payment failed") have no delivery guarantees today.

We need to decouple notification delivery from request processing, add retry with exponential backoff, guarantee at-least-once delivery for billing events (exactly-once where feasible), and prepare for real-time WebSocket push within two quarters. The system must handle 10× traffic growth (~5,000 req/s peak) without re-architecting.

Key constraints:

- **Team**: 6 engineers, no dedicated infrastructure engineer, zero Kafka operational experience.
- **Timeline**: must deliver value within 2 weeks of starting migration.
- **Existing infrastructure**: Redis already in production for sessions and rate limiting; PostgreSQL as the primary data store.
- **Budget**: modest — managed Confluent Cloud at full scale is not affordable.
- **Correctness requirement**: exactly-once semantics for billing notifications.

## Decision

> We will use Redis Streams as the message broker for the notification subsystem.

Redis Streams handles our throughput ceiling (5,000 msg/s peak after 10× growth) with wide margin, requires no new infrastructure, and can be operational within the 2-week constraint. Exactly-once delivery for billing notifications will be enforced at the application layer using idempotency keys stored in PostgreSQL, not by the broker itself.

## Rationale

### Throughput

Redis Streams sustains hundreds of thousands of messages per second on a single instance. Our 10× growth target peaks at ~5,000 msg/s — well within Redis capacity even with headroom for burst and consumer-group overhead. Kafka's millions-of-messages-per-second throughput is a capability we do not need and will not need at projected scale.

### Ordering guarantees

Redis Streams provide strict per-stream insertion order (all consumers see messages in the order they were appended), which is stronger than Kafka's per-partition ordering. For our use case — a single logical notification stream per event type — this is simpler to reason about and eliminates the partition-key design decisions Kafka requires.

### Message retention

Kafka offers configurable long-term retention (days to weeks of replay), which Redis Streams does not natively match. Our notification system does not need historical replay beyond a short failure-recovery window. Redis Streams' `MAXLEN` trimming with a generous cap (e.g., 100,000 messages per stream) keeps memory bounded while retaining enough backlog for consumer recovery. Notifications that require permanent audit trails will be persisted in PostgreSQL alongside the event record — the broker is a delivery mechanism, not the system of record.

### Consumer groups

Redis Streams support consumer groups via `XREADGROUP` and `XACK`, with `XCLAIM` for message recovery after consumer failure. This covers our requirements: multiple notification workers consuming in parallel, automatic message redistribution on worker failure, and explicit acknowledgment. Kafka's consumer group protocol is more mature (automatic rebalancing, session timeouts, cooperative sticky assignment), but our consumer topology is simple — a fixed pool of workers per stream — and does not need Kafka's more sophisticated coordination.

### Exactly-once semantics

Neither Redis Streams nor Kafka provides true exactly-once delivery without application-level cooperation. Kafka's transactional producer/consumer reduces duplicate surface area but does not eliminate it under consumer failure scenarios. For billing notifications, we will use the same pattern that works on both brokers: write an idempotency key to PostgreSQL before publishing, and check it on delivery. This makes the broker-level exactly-once guarantee non-essential — the application layer enforces it.

### Operational complexity

This is the decisive constraint. Redis is already running in production. The team knows how to monitor, back up, and troubleshoot it. Adding Streams is a feature enablement on existing infrastructure — no new daemons, no ZooKeeper/KRaft cluster, no partition rebalancing to manage, no new monitoring stack. Kafka introduces a separate distributed system with its own failure modes, operational runbooks, and on-call burden. With no dedicated infrastructure engineer and no Kafka experience on the team, the risk of misconfiguration and prolonged incidents is real and has no mitigating investment within the 2-week window.

### Time to value

A Redis Streams-based notification worker can be prototyped in days using the team's existing Python stack and Redis connection. Kafka would require provisioning a cluster (self-managed or managed), learning administrative operations, and building client code against a new paradigm — realistically 4–6 weeks before first production delivery, exceeding the constraint.

### Cost

Redis is already paid for. Self-managed Kafka on EC2 requires minimum 3 brokers for fault tolerance, plus monitoring. Managed Confluent Cloud starts at a meaningful monthly cost and escalates with throughput. Neither fits a modest budget for a notification subsystem that processes low thousands of messages per second.

## Alternatives Considered

- **Apache Kafka** — rejected because the team has zero operational experience with it, the 2-week delivery constraint cannot be met with a new distributed system, and the budget cannot absorb managed Confluent at scale. Kafka's advantages in throughput, long-term retention, and mature consumer group rebalancing are real but irrelevant at our scale and timeline. We would reconsider Kafka if: traffic grew 50× beyond current projections (sustained >25,000 msg/s), we needed multi-team event streaming across organizational boundaries, or we hired dedicated infrastructure engineers and allocated budget for managed Kafka.

- **PostgreSQL LISTEN/NOTIFY** — rejected because it provides no persistence (messages are lost if no consumer is connected), no consumer groups, and no retry mechanism. It is a notification mechanism, not a message broker. Suitable only for lightweight real-time signals within a single process boundary.

- **RabbitMQ** — rejected because it introduces a new infrastructure dependency with comparable operational overhead to Kafka (cluster management, monitoring, on-call burden) without Kafka's extreme throughput advantage. Redis Streams already covers our use case with less operational cost.

## Consequences

- **Positive**: Faster time to production (days, not weeks). No new infrastructure to operate. Team can leverage existing Redis knowledge for monitoring, alerting, and troubleshooting. Simpler architecture — one fewer distributed system in the stack. Natural path to WebSocket push via Redis Pub/Sub in the second phase.
- **Negative**: Redis Streams lack Kafka's long-term retention and replay capabilities. If a future requirement demands historical event replay across days or weeks, we will need to add a separate persistence layer or reconsider Kafka. Consumer group rebalancing in Redis is less sophisticated — workers must handle message claiming explicitly via `XPENDING`/`XCLAIM` rather than relying on automatic rebalancing. Redis is a single point of failure for the notification subsystem unless we configure Redis Sentinel or Cluster, which adds complexity we should plan for in a follow-up.
- **Follow-ups**:
  1. Implement idempotency-key table in PostgreSQL for billing notifications before wiring the first producer.
  2. Set up Redis persistence (AOF with `fsync everysec`) and Sentinel for high availability as part of the migration.
  3. Build the notification worker service with `XREADGROUP`, explicit `XACK`, and `XCLAIM`-based dead-letter logic.
  4. Add `MAXLEN ~100000` to each stream to bound memory.
  5. Plan Redis Pub/Sub integration for WebSocket push in the next quarter.
  6. Re-evaluate Kafka if sustained throughput exceeds 25,000 msg/s or if multi-team event streaming becomes a requirement.