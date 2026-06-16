# ADR-001: Notification Subsystem — Async Processing with Redis Streams

**Status:** Proposed

**Date:** 2026-06-16

## Context

The SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) sends email and webhook notifications when tasks are updated, assigned, or completed. Notifications are sent synchronously inside the HTTP request cycle, causing four interconnected problems:

1. **Request timeouts** — average 800ms added latency, spiking to 8s during peak hours.
2. **Silent failures** — when an email provider or webhook endpoint is unreachable, the notification is dropped with no retry or dead-letter capture.
3. **Cascading failures** — two incidents this year where a slow webhook caused PostgreSQL connection pool exhaustion, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") need exactly-once delivery; the current system provides none.

We need an async notification subsystem that decouples notification delivery from HTTP request handling, supports retry with exponential backoff, provides at-least-once delivery with exactly-once semantics for billing events, and can be extended to real-time WebSocket push within two quarters — all while handling 10x current traffic.

### Key constraints

| Constraint | Impact |
|---|---|
| Team of 6 (3 senior, 3 mid), no dedicated infra engineer | Operational simplicity is a first-order requirement |
| Redis already in production (session storage, rate limiting) | Existing operational knowledge; no new daemon to run |
| No Kafka experience on the team | Kafka adoption means a steeper learning curve, hiring pressure, or both |
| Must deliver value within 2 weeks of start | Rules out technologies with non-trivial cluster setup |
| Budget is modest — managed Confluent Cloud not an option | Self-hosted Kafka carries its own operational cost |
| Exactly-once semantics required for billing notifications | Drives the choice of ack/retry/dead-letter mechanism |

## Decision

**Use Redis Streams as the notification backbone.**

Notification producers (`XADD` a message to a stream) and notification consumers (`XREADGROUP` within a consumer group, `XACK` after successful delivery, `XPENDING` for retry tracking) replace the current synchronous delivery path. A dead-letter stream captures messages that exhaust their retry budget.

We will implement exactly-once delivery for billing notifications at the **application layer** — each billing event carries a deduplication key (idempotency key) stored in Redis with a TTL; consumers check and record the key before processing. At-least-once delivery via consumer group acknowledgments suffices for non-billing notifications.

### Architecture sketch

```
HTTP Request → Flask handler
                    │
                    ▼
           ┌────────────────┐
           │  Redis Stream   │  (XADD with notification payload)
           │  "notifications"│
           └───────┬────────┘
                   │
          XREADGROUP (consumer group)
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
    Email      Webhook    WebSocket
    Worker     Worker     Worker (Q2)
        │          │          │
        ▼          ▼          ▼
   XACK +     XACK +     XACK +
   retry      retry      retry
   (DLQ)      (DLQ)      (DLQ)
```

## Consequences

### Benefits

| Dimension | Assessment |
|---|---|
| **Time to value** | Redis Streams can be productive within days. The `redis-py` library already supports `XADD`, `XREADGROUP`, `XACK`, and `XPENDING` natively. No new infrastructure, no cluster bring-up, no new daemon to monitor. |
| **Operational complexity** | Near-zero incremental complexity. The team already manages Redis for sessions and rate limiting. Streams are a data type, not a separate service. Redis persistence (RDB/AOF), replication (Sentinel), and monitoring (INFO, SLOWLOG) are known quantities. |
| **Throughput** | Redis handles 100k+ ops/sec on a modest instance. At current peak (500 req/s), even assuming 5 notifications per request (2,500 writes/sec), we are at ~2.5% of Redis's capacity. 10x growth (25,000 writes/sec) is still well within reach. If needed, Redis Cluster shards streams across nodes trivially. |
| **Ordering guarantees** | Redis Streams guarantee insertion order within a single stream shard. For per-task ordering, use a stream sharded by `task_id`. This is functionally equivalent to Kafka's per-partition ordering. |
| **Consumer groups** | `XREADGROUP` with `XACK` provides at-least-once delivery with automatic pending-message tracking via `XPENDING`. Dead-letter support is straightforward: after N retries, `XADD` the message to a `notifications:dlq` stream and `XACK` the original. |
| **Message retention** | Bounded by `MAXLEN ~ 100000` to cap memory usage. For archival needs (audit trails, billing forensics), messages are written to PostgreSQL in the consumer before acknowledgment — this is a one-line `INSERT` in the worker. Kafka's disk-based retention buys nothing here because we already have a durable database. |
| **Real-time WebSocket push** | Redis Pub/Sub or a lightweight Streams consumer can feed a WebSocket relay with minimal additional infrastructure. No Kafka needed. |
| **Exactly-once for billing** | Kafka's EOS is a broker-level guarantee — but it comes with strict constraints (transactional producers within a single Kafka cluster, no cross-system transactions). Our billing notification must be processed exactly once *in our database*, which is PostgreSQL. True distributed exactly-once across Kafka + PostgreSQL would require a distributed transaction or a transaction outbox pattern anyway. Redis Streams + application-level idempotency keys achieves the same result with less complexity: generate a `dedup_key = sha256(event_id + notification_type)`, `SET dedup_key 1 EX 86400 NX`, skip if key already exists. This pattern is well-documented and proven in production. |
| **Cost** | Zero new infrastructure cost. Existing Redis instance handles the additional load. No brokers, no ZooKeeper nodes, no MSK cluster to provision. |

### Trade-offs and risks

| Risk | Mitigation |
|---|---|
| **Memory-bound retention** — Redis stores streams in RAM. If consumers fall behind significantly, the stream backlog grows and consumes memory. | Set `MAXLEN ~ 100000` to bound the stream size. Monitor stream length with `XLEN` and alert at 80% of the cap. If consumers fall behind further, scale up consumers (they're idempotent) or temporarily increase `MAXLEN`. Kafka's disk-based retention looks appealing here, but in practice a backlog this large means consumers are broken — fix the consumer, don't provision for infinite backlog. |
| **No automatic consumer rebalancing** — Kafka reassigns partitions when a consumer joins or leaves a group. Redis requires manual claiming of pending messages via `XCLAIM` or `XAUTOCLAIM`. | `XAUTOCLAIM` (Redis 6.2+) automates this: pending messages that haven't been acknowledged within a timeout window are automatically reassigned. This is equivalent to Kafka's `session.timeout.ms` + rebalance protocol, but simpler — no rebalance storm, no StopTheWorld rebalancing. |
| **No built-in exactly-once** — Redis Streams do not have Kafka's transactional producer protocol. | The application-layer idempotency key pattern (described above) is the standard approach used by Stripe, AWS, and others. It is strictly more general than broker-level EOS because it works across system boundaries (Redis → PostgreSQL, not just within Kafka). |
| **Redis memory cost at extreme scale** — If we reach 50k+ writes/sec with large payloads, RAM costs can exceed Kafka's disk costs. | At 10x growth (2,500–25,000 writes/sec), the stream throughput is within Redis's sweet spot. If we hit the extreme scale where memory becomes cost-prohibitive, we can migrate to Kafka at that point — the stream abstraction (produce → consume → ack) is the same mental model, so the migration is architectural, not conceptual. |
| **Single point of failure** — Redis (even with Sentinel) is less resilient than a multi-broker Kafka cluster. | Our Redis already runs with Sentinel or replication for session storage — it is not single-node. If Redis is down, sessions and rate limiting are also down, so we already have incident response for that failure mode. Kafka's resilience advantage is real but irrelevant when you already depend on Redis for core functionality. |

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the industry standard for event streaming and, on paper, checks every technical box:

- **Exactly-once semantics** via transactional producers and idempotent writes.
- **Disk-based retention** — retain messages for days or weeks regardless of consumer progress.
- **Automatic consumer rebalance** — Kafka's group coordinator handles partition assignment.
- **Proven at enormous scale** — 1M+ msgs/sec is routine.

We rejected Kafka for the following reasons, weighted by the constraints in this context:

**Operational complexity is the dealbreaker for a 6-person team.** A production Kafka deployment requires: ZooKeeper or KRaft cluster (3 nodes minimum), broker tuning (heap, page cache, disk I/O scheduler, partition counts, ISR configuration, unclean leader election policy), consumer group monitoring (lag, rebalance, offset commit failures), and ongoing maintenance (broker upgrades, partition reassignment, disk replacement). Each of these has inflicted production incidents on teams far larger than ours. The team has zero Kafka experience today — operating it reliably would take 3–6 months of seasoning, during which time the notification subsystem would remain broken.

**2-week delivery timeline is incompatible with Kafka setup.** Even using AWS MSK (managed Kafka), provisioning a cluster and getting a Python consumer stack (`confluent-kafka` or `kafka-python`) into production with proper error handling, exactly-once configuration, and monitoring is a 4–6 week project for a team new to Kafka. The problem is already causing production incidents — we need a solution in days, not months.

**Cost is a secondary but real concern.** MSK starts at ~$0.50/hr per broker (3 brokers minimum = ~$1,080/month), plus storage at $0.10/GB-month provisioned. For our current volume (~2,500 notifications/sec peak), this is idle capacity. Confluent Cloud is more expensive still and explicitly ruled out. Meanwhile, Redis handles the load on existing infrastructure at zero marginal cost.

**Kafka is overkill for this problem.** A notification queue for a SaaS platform at 500 req/s is not a high-throughput event streaming problem. It is a queue-with-retry problem. Redis Streams were designed for exactly this use case (the `XADD` / `XREADGROUP` / `XACK` / `XPENDING` API is practically a queue abstraction). Using Kafka here would be paying the complexity tax of a distributed log for what is, at its core, a producer-consumer workload.

**The EOS advantage is narrower than it appears.** Kafka's exactly-once semantics operate within a single Kafka cluster. For billing events that must be processed exactly once in PostgreSQL (the durable record of truth), we would still need either: (a) a transaction outbox pattern (write to an outbox table in the same PostgreSQL transaction as the business operation, then have a separate process publish to Kafka), or (b) a distributed transaction across Kafka and PostgreSQL (Kafka's EOS + PostgreSQL XA, which is operationally complex and avoided in practice). Either way, the application-layer idempotency approach is what production systems actually use — Kafka's EOS buys very little for cross-system workflows.

## Implementation Plan (2 Weeks)

| Day | Milestone |
|---|---|
| 1–2 | Create notification stream, consumer group, and dead-letter stream in existing Redis. Write `NotificationProducer` service (`XADD` with payload + dedup key for billing events). |
| 3–5 | Write `NotificationConsumer` base class (`XREADGROUP` → process → `XACK` → error → retry logic → dead-letter). Implement `EmailConsumer` and `WebhookConsumer`. |
| 6–7 | Wire the Flask handler to call `NotificationProducer` instead of sending synchronously. Remove blocking email/webhook calls from the request cycle. |
| 8–10 | Add retry with exponential backoff (`XADD` back to stream with `retry_count + 1`; dead-letter at max 5 retries). Add monitoring: `XLEN` stream depth, `XPENDING` count, consumer lag. |
| 11–14 | Load test at 10x current traffic. Deploy to staging, then production with feature flag. Decommission sync notification code. |

## Conclusion

Redis Streams are the correct choice for this system and this team. They solve the immediate problems (timeouts, silent failures, cascading failures) within the 2-week constraint, leverage existing operational knowledge, and leave room to grow (WebSocket push, higher throughput, consumer scaling) without over-investing in infrastructure we do not yet need. Kafka's superior feature set is real but irrelevant here — the marginal benefit of broker-level EOS and disk-based retention does not justify the step-change in operational complexity for a 6-person team with no Kafka experience.
