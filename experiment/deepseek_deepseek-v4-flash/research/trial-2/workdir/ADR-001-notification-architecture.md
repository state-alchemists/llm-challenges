# ADR-001: Notification Subsystem — Async Decoupling with Redis Streams

**Status:** Proposed  
**Date:** 2026-07-29  
**Author:** Engineering Team  
**Deciders:** All (6)

---

## Context

The notifier subsystem sends emails and webhooks when tasks are updated, assigned, or completed. It currently runs synchronously inside the HTTP request cycle of a Python/Flask monolith (~50k lines). As the platform has grown to 85,000 monthly active users and ~2M tasks/month (peak 500 req/s), this design has produced three classes of production failures:

1. **Request timeouts** — average notification latency of 800 ms, spiking to 8 s during peak hours, blocking the HTTP response.
2. **Silent failures** — email provider or webhook endpoint outages cause the notification to be dropped immediately. No retry, no dead-letter queue.
3. **Cascading failures** — two incidents this year where a slow webhook endpoint exhausted the connection pool, taking down unrelated features (task creation, authentication).

Billing-critical notifications ("trial expired", "payment failed") require assured delivery, but the current system provides no delivery guarantees at all.

### Scaling Target

- Decouple notifications from the HTTP request cycle (async processing).
- Support retry with exponential backoff.
- At-least-once delivery for billing events; exactly-once where feasible.
- Real-time WebSocket push notifications within two quarters.
- Handle 10× traffic growth without re-architecting the notification pipeline.

### Constraints

- **Team:** 6 engineers (3 senior, 3 mid-level). No dedicated infrastructure or SRE engineer.
- **Existing infrastructure:** Redis in production today for session storage and rate limiting. PostgreSQL (1 primary, 1 read replica), 4 web servers behind nginx on AWS.
- **Kafka experience:** None on the team today.
- **Timeline:** Must deliver value within 2 weeks of setup and migration work.
- **Budget:** Modest. Cannot afford managed Confluent Cloud at full scale currently.
- **Billing requirement:** Exactly-once semantics for billing notifications.

---

## Decision

**We will build the async notification subsystem using Redis Streams.**

Redis Streams will serve as the message broker between the Flask monolith (producers) and a new consumer service (consumers) that handles email dispatch, webhook delivery, and — within two quarters — WebSocket fan-out. The existing Redis instance will be scaled up (or a dedicated Redis instance provisioned for streams) to separate the notification workload from session/rate-limiting traffic.

### Architecture Outline

```
HTTP Request → Flask handler → XADD stream (Redis Streams)
                                       │
                                       ▼
                            Consumer Worker(s)
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                     Email API    Webhook     Dead-Letter Queue
                     (SMTP/SES)   HTTP POST   (Redis stream + alert)
```

```
WebSocket Push (Q2):
                    Redis Streams → Consumer Worker → Redis Pub/Sub
                                                           │
                                                           ▼
                                                     WebSocket Server(s)
```

- **Producer side:** Flask handler writes a structured JSON message to a Redis stream (`stream:notifications`) via `XADD`. The HTTP response is returned immediately after the write succeeds (~1-5 ms added). No external API calls are made in the request path.
- **Consumer side:** A lightweight Python service uses `XREADGROUP` with consumer groups to claim and process messages. Retries use `XCLAIM` and `XPENDING` for visibility into stalled deliveries. Messages that exhaust the retry limit are moved to a dead-letter stream (`stream:dlq`).
- **Deduplication for billing:** A PostgreSQL `notification_delivery` table stores delivery results keyed by a client-generated idempotency key. Consumers check this table before dispatching billing notifications to guarantee at-most-once processing downstream.
- **WebSocket (Q2):** The same consumer worker publishes events to Redis Pub/Sub, which WebSocket servers subscribe to for real-time push.

---

## Consequences

### Advantages

| Property | Why Redis Streams Wins |
|---|---|
| **Time to value** | Redis is already in production. The team can write and deploy stream-based code within days, not weeks. The 2-week deadline is easily met. |
| **Operational familiarity** | Every engineer on the team already understands Redis operations, monitoring, and failure modes (AOF/RDB persistence, replication, eviction policies). No new system to learn under production pressure. |
| **Throughput headroom** | Single-instance Redis handles 100k+ operations/s. At 500 req/s peak (5,000 at 10×), the notification workload is well within Redis's capability — even with consumer group overhead. |
| **Zero incremental infrastructure** | Redis Streams is a data type, not a new service. If the existing instance has headroom, cost is $0. Even a dedicated instance (e.g., ElastiCache cache.r6g.large) is ~$100-150/mo — within a modest budget. |
| **Ordering** | Messages within a single stream maintain strict insertion order. For notifications that don't need ordering (most use cases), a single stream suffices. For ordered processing (e.g., per-task update history), producers write to a task-scoped stream key. |
| **Consumer groups** | `XREADGROUP` provides exactly-once *delivery* semantics within Redis — each message is delivered to exactly one consumer in the group. The pending entries list (`XPENDING`) and claim mechanism (`XCLAIM`) provide visibility and recovery for stalled consumers. |
| **WebSocket path** | Redis Pub/Sub is a natural, well-documented fit for WebSocket fan-out. The same Redis instance handles both stream processing and real-time push, avoiding cross-system integration. |

### Disadvantages and Mitigations

| Limitation | Impact | Mitigation |
|---|---|---|
| **No automatic partition rebalancing** | Adding or removing consumers requires manual group coordination. Kafka rebalances partitions automatically; Redis Streams does not. | At our scale (single stream, 2-4 consumers), manual assignment is tractable. A simple health-check + XCLAIM loop handles transient failures. Document the process for scaling consumers. |
| **Memory-bound retention** | Streams live in Redis memory. Unlimited retention is expensive. Long-lived consumers that fall behind can cause OOM. | Cap stream length via `MAXLEN ~ 100,000` (approximate trimming). Billing events are acknowledged and deduplicated in PostgreSQL — the stream is a transport, not a store. Monitor stream length with a metric alert. |
| **No built-in exactly-once semantics** | Redis Streams provides at-least-once delivery. Restarting a worker after a crash may reprocess acknowledged-but-uncommitted messages. | This is the same reality for Kafka — Kafka's exactly-once semantics apply *within Kafka* but do not extend to external HTTP calls (email APIs, webhooks). Both solutions require consumer-side deduplication for end-to-end exactly-once. Our PostgreSQL `notification_delivery` table with idempotency keys fills this gap. |
| **Slower catch-up from cold start** | Kafka's disk-based log allows new consumers to replay months of history cheaply. Redis Streams must replay from the in-memory tail. | Not a problem for our use case. Notifications older than the current stream window are either delivered or in the PostgreSQL dedup table. We do not need replay of month-old events. |
| **Future scalability ceiling** | At 100× growth (50,000 req/s) or when the team grows to 20+ engineers, Kafka's architectural advantages (disk-based log, automatic rebalancing, Schema Registry, ecosystem integrations) become compelling. | Cross that bridge when it arrives. The cost of migrating from Redis Streams to Kafka is bounded: the producer writes `XADD` — replacing it with `producer.send()` is a few dozen lines of code. The consumer's business logic (email dispatch, webhook, dedup) is unaffected; only the read loop changes. The team will have 12-24 months of growth before this becomes urgent. |

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the industry standard for event streaming, and its feature set — disk-based retention, automatic consumer rebalancing, partitioning for parallel throughput, Kafka Connect ecosystem, exactly-once source semantics — is objectively superior to Redis Streams for a large-scale event pipeline.

**Why we are rejecting it for this decision:**

| Criterion | Assessment |
|---|---|
| **Team capability** | Zero Kafka experience among 6 engineers, with no SRE support. Kafka's failure modes (leader election, ISR management, unclean leader election, log compaction, consumer lag, partition skew, rebalancing storms) are well-documented but require hands-on experience to diagnose. The learning curve would delay value delivery by several weeks at minimum. |
| **Operational cost** | Self-hosted Kafka requires at least 3 brokers (each 4-8 GB RAM), ZooKeeper (or KRaft), and EBS volumes with careful tuning of retention, replication, and segment settings. That is 3-6 new EC2 instances to learn, configure, and monitor. Managed Confluent Cloud at our current scale (~1 GB/day) starts at ~$300-500/mo and scales non-linearly. The constraints say "modest budget" and "no dedicated infrastructure engineer." |
| **Timeline conflict** | The constraint "must not require more than 2 weeks of setup/migration work before delivering value" is incompatible with introducing Kafka to a team of 6 with zero Kafka experience. Two weeks covers broker provisioning and basic topic setup — not the consumer architecture, the retry/backoff/DDL system, and production hardening. |
| **Overkill for current scale** | 500 req/s (5,000 at 10×) does not require Kafka's throughput. Kafka excels at millions of events per second, multi-subscriber topologies, and long-term event storage. We have none of these needs today. The operational overhead of Kafka for this throughput is disproportionate. |

**When we might want Kafka:** If the team grows to 12+ engineers (including an infrastructure engineer), event volume exceeds 20,000 req/s, we need indefinite event replay, or we adopt event sourcing / CQRS patterns, Kafka becomes the right choice. The ADR for that migration will be simpler because the consumer business logic (the expensive part) stays the same.

### Managed Queue Services (SQS + SNS) — Not formally evaluated per scope

AWS SQS + SNS would also solve the synchronous-notification problem with zero operational overhead. We chose Redis Streams because Redis is already in our stack and SQS's at-least-once delivery with 14-day retention is sufficient for notifications. The primary reason SQS was not our top choice is the team's explicit interest in WebSocket push within two quarters — Redis Pub/Sub provides a natural bridge that SQS alone does not (SNS + WebSocket requires Lambda + API Gateway, adding cost and complexity). If the team prefers to minimize infrastructure, SQS is a valid re-evaluation candidate.

---

## Exactly-Once Semantics: A Clarification

Both Kafka's *exactly-once semantics* and Redis Streams' *at-least-once delivery* apply to the broker-consumer channel. Neither provides end-to-end exactly-once delivery to an external system (an email API, a webhook endpoint):

- **Kafka EOS** guarantees that a message is produced to the topic exactly once and consumed exactly once *within the Kafka ecosystem*. If the consumer crashes after processing but before committing the offset, the message is replayed — and the downstream API call may already have succeeded.
- **Redis Streams** consumers acknowledge (`XACK`) a message after processing. A crash before `XACK` causes reprocessing.

In both cases, **true exactly-once delivery to an external API requires an idempotent receiver or a deduplication table**. Our PostgreSQL `notification_delivery` table, keyed by a notification-level idempotency ID, serves this purpose. This means the exactly-once requirement does not advantage Kafka over Redis Streams in any meaningful way — both need the same consumer-side dedup.

---

## Recommendation

**Use Redis Streams.** Ship the async notification subsystem within two weeks. The decision is driven by three unforced errors that Kafka would introduce: operating a new distributed system with no team experience, spending time and budget on infrastructure that exceeds current scale requirements, and delaying time-to-value past a hard 2-week constraint. Redis Streams solves all four stated problems (timeouts, silent failures, cascading failures, no delivery guarantees) today, and leaves a well-understood migration path to Kafka when the company's scale demands it.

### Immediate Next Steps

1. Provision a dedicated Redis instance for streams (separate from session/rate-limiting).
2. Implement `XADD` in the Flask request handlers for notifications (3-5 days).
3. Build consumer worker with `XREADGROUP`, retry loop, and dead-letter stream (4-6 days).
4. Implement PostgreSQL idempotency table for billing notifications (2 days).
5. Deploy, monitor, retire synchronous notification path (1 day).
6. Ship.
