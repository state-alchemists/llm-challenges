# ADR-001: Notification Subsystem — Async Architecture

**Status:** Proposed

---

## Context

We run a SaaS project management platform (~85,000 MAU, ~2M tasks/month, ~500 req/s peak). The notification module — email and webhook delivery on task updates, assignment, and completion — currently blocks the HTTP request cycle. This has produced four concrete failures:

1. **Request timeouts** — 800ms average latency, 8s spikes during peak. Notifications are IO-bound and unpredictable.
2. **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry, no dead-letter queue, no operator signal.
3. **Cascading failures** — two P0 incidents in the past year where a slow webhook caused connection pool exhaustion, taking down task creation and other unrelated endpoints.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") have no at-least-once or exactly-once guarantee.

The engineering team is 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We already run Redis in production for session storage and rate limiting. Nobody on the team has production Kafka experience. The migration must deliver value within 2 weeks and support 10x traffic growth without re-architecting. Budget cannot absorb managed Confluent Cloud at full scale.

Two candidates emerged for the async message backbone: **Apache Kafka** and **Redis Streams**.

---

## Decision

**We will use Redis Streams as the notification message backbone.**

### Justification

**Fit to scale, not peak throughput.** Our current peak is ~500 req/s. At 10x growth we need ~5,000 notification events/s. Redis Streams handles this comfortably on modest hardware — the bottleneck will be the consumer workers, not the stream. Kafka's multi-broker partitioning and 1M+ msg/s throughput are wasted on this load profile and would add operational surface area we don't need.

**No new infrastructure, no new ops knowledge.** Redis is already deployed, monitored, and backed up. Our team knows its failure modes — latency spikes under memory pressure, failover behavior, persistence tuning. Kafka would introduce a JVM process, Zookeeper or KRaft controller quorum, disk layout planning, partition rebalancing, and a new skill set the entire team would need to ramp on. With no dedicated infra engineer, that's a bet on learning under production pressure.

**Retry and dead-letter handling are first-class.** Redis Streams provides a Pending Entry List (PEL) per consumer group. When a consumer claims a message and fails to acknowledge it, the message stays in the PEL. A separate consumer (or a timed reaper) can inspect the PEL, inspect delivery counts via `XINFO GROUPS`, and route exhausted retries to a dead-letter stream. This maps directly to our retry-with-exponential-backoff requirement with zero custom queue infrastructure.

**Consumer groups enable WebSocket push.** The upcoming real-time WebSocket feature (target: 2 quarters) maps naturally to a separate consumer group reading the same stream — one group for email/webhook dispatch, another for WebSocket fan-out. Kafka supports this too, but Redis Streams does it without adding a second system.

**Delivers value inside the 2-week window.** We can go live with a minimal pipeline in days: produce to a stream from the Flask request handler (non-blocking via Redis async client or background thread), run a Python consumer process with `XREADGROUP`, implement idempotent delivery with a simple dedup table in PostgreSQL. Kafka, by contrast, would first require provisioning a cluster, learning the CLI, tuning producer/consumer configs, and debugging a system nobody on the team has operated.

### On exactly-once delivery for billing

Kafka advertises exactly-once semantics (EOS) via transactional producers and idempotent consumers. In practice, EOS in Kafka requires producer transactions, consumer transaction isolation, and careful coordination of offsets — it's complex, fragile under rebalancing, and still only guarantees exactly-once *within the Kafka cluster*, not end-to-end (your email provider can still receive a duplicate).

A simpler approach that meets the same bar: produce billing notifications idempotently (dedup by event ID in PostgreSQL), and make consumers idempotent (check `notification_id` before sending). This achieves end-to-end exactly-once semantics without Kafka's transactional machinery, and it works identically whether the message comes from Kafka or Redis Streams. Redis Streams does not lose this ground; the application is the right layer to enforce this guarantee regardless of transport.

---

## Consequences

### Pros

- **Zero new infrastructure.** Redis is already deployed, monitored, and understood. No new cluster, no new alarms, no new on-call surface.
- **Fast time-to-value.** A working pipeline can ship inside one sprint. The team can focus effort on consumer logic (retry, idempotency, WebSocket) instead of cluster operations.
- **Natural retry story.** The PEL gives us pending-message tracking and redelivery out of the box. `XCLAIM` lets a retry worker re-assign stalled messages after a configurable visibility timeout — the same pattern used by SQS and Celery.
- **Good fit for expected scale.** 5,000 evt/s is well within a single Redis instance's throughput. At 10x we add worker processes, not brokers.
- **Dead-letter stream is trivial.** `XADD` to a `notification-dlq` stream when retries exhaust. Alert on stream length.
- **WebSocket fan-out is additive.** A second consumer group reads the same stream. No architectural change, no second message bus.
- **Consumer groups scale horizontally.** Multiple consumer processes reading the same group partition messages among themselves. Failure of one leaves the others processing.
- **Memory profile is manageable.** At ~1 KB per notification event (typical JSON payload), 5,000 events/s × 24h retention = ~430 GB for a full day. With 8h retention and compression, this drops to ~140 GB — feasible on a Redis instance with fast disk-backed persistence (AOF). For longer retention, archive to S3 via a background consumer.

### Cons

- **No built-in long-term retention.** Redis is memory-first. Streaming 30 days of events for replay requires an archival consumer writing to S3/PostgreSQL. Kafka stores to disk and can retain indefinitely without special plumbing.
- **Exactly-once is application-layer only.** Redis Streams provides no transactional producer semantics. We must implement idempotency at the consumer (dedup table) and, for billing-critical messages, use a transaction that atomically claims the message and inserts the dedup record. This is well-understood but must be written and tested rather than configured.
- **Single-node write bottleneck.** Redis Streams writes go through a single primary. At our scale (5,000 evt/s) this is trivial, but if the platform grows 100x instead of 10x, we'd need Redis Cluster or a sharding layer. Kafka partitions across brokers from day one.
- **Consumer group rebalancing is simpler than Kafka but not seamless.** When consumers join or leave a group, `XREADGROUP` auto-redirects, but there is no partition rebalancing protocol — some consumers may briefly idle. Mitigation: use enough consumer processes, and accept that idle time at the 95th percentile is tolerable at our latency SLOs (seconds, not milliseconds).
- **Stream-replication lag in failover.** If the Redis primary fails and a replica is promoted, unacknowledged messages may be lost if `stream-node-max-bytes` or AOF sync lagged. Mitigation: `WAIT` for replica acknowledgment on billing-critical writes, and run Redis with AOF + fsync=always for the notification stream (trading some write throughput for durability).
- **No native stream compaction.** Kafka's log compaction retains only the latest value per key — useful for state snapshots. Redis Streams does not compact. Not a problem for our use case (notification events are fire-and-forget append log), but worth noting.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka was rejected because its strengths do not match our constraints.

| Dimension | What Kafka Offers | What We Need | Gap |
|-----------|-------------------|--------------|-----|
| Throughput | Millions msg/s per broker | 500–5,000 evt/s | Overkill — adds complexity without benefit |
| Ordering | Per-partition, strong | Per-task-id ordering sufficient; PostgreSQL idempotency handles rest | No material advantage at this scale |
| Retention | Disk-based, configurable, indefinite | Hours-to-days for retry; archive to S3 beyond that | Useful but not worth the ops cost |
| Exactly-once | Transactional producer + idempotent consumer | End-to-end exactly-once for billing | Kafka's EOS still doesn't cover the last mile (email/webhook endpoint) — we need application idempotency either way |
| Consumer groups | Mature, rebalance-aware, offset management | Parallel consumption, retry, dead-letter | Redis Streams PEL provides the same primitives at lower complexity |
| Operations | Zookeeper or KRaft, JVM tuning, disk provisioning, partition sizing, rebalance monitoring | Team of 6, no infra engineer | Overwhelming — a Kafka cluster is a full-time operational responsibility |
| Team experience | Zero | Redis: daily | Learning curve alone violates the 2-week delivery constraint |

**The tipping point:** The 2-week delivery constraint. A team learning Kafka from scratch cannot provision a production cluster, build the pipeline, and validate exactly-once semantics for billing within 2 weeks. Redis Streams can demonstrate a working, monitored pipeline in 3–5 days.

**When Kafka would become the right choice:** If our event throughput exceeded ~50,000 msg/s, or if we needed indefinite log retention for audit replay, or if we grew to a size where a dedicated infrastructure engineer was on the team. At that point, the migration path is straightforward: dual-write to both systems during transition, then cut over consumers.

### AWS SQS / SNS (Deferred, not rejected)

SQS offers managed queues with exactly-once (FIFO, 300 TPS) and at-least-once (standard, unlimited TPS). SNS adds pub/sub fan-out. Both require zero operations. We deferred this option because:

- FIFO queues are limited to 300 TPS — too tight for 10x growth on billing events without partitioning across multiple queues manually.
- SQS visibility timeout is capped at 12 hours (max) for retry — too short for our exponential-backoff retry policy with a DLQ.
- SNS does not support consumer groups or PEL-style pending-list inspection. We'd need SQS as the subscriber + custom retry logic on top.
- AWS spend at 5,000 evt/s × 30 days: ~$400–600/month for SQS/SNS alone, not counting Lambda or EC2 consumer costs. Redis is already paid for.
- Lock-in concern: once on SQS/SNS, the team builds around AWS-specific primitives (redrive policy, DLQ ARN, Lambda triggers). Redis Streams is portable to any deployment model.

We are not rejecting SQS/SNS permanently — if the team grows and wants zero-ops messaging for non-billing workflows, SQS is a natural secondary system. But for this decision, Redis Streams gives us more control for the same (or lower) total cost.

---

## Implementation Outline

```
┌──────────────┐     XADD      ┌──────────────────┐
│  Flask App   │──────────────▶│  Redis Stream    │
│ (producer)   │               │  notif:events     │
└──────────────┘               └────────┬─────────┘
                                        │
                           ┌────────────┴────────────┐
                           │                         │
                    XREADGROUP                  XREADGROUP
               ┌────┴────┐                ┌────┴────┐
               │ Consumer│                │ Consumer│
               │ Group A │                │ Group B │
               │ (email/ │                │(websock)│
               │ webhook)│                └─────────┘
               └────┬────┘
                    │
          ┌─────────┴──────────┐
          │                    │
     Send email         Mark done
     / webhook          (XACK)
          │
          │ on failure
          ▼
    PEL retry (XCLAIM)
    ── exponential backoff
    ── max 5 attempts
    ── then XADD to DLQ
```

**Migration plan (2 weeks):**

1. **Day 1–2:** Stream schema design. Add Redis Stream `XADD` to notification producer code (wrapped in a thread or async task so the HTTP handler doesn't wait).
2. **Day 3–5:** Build a Python consumer using `XREADGROUP`. Implement the core dispatch loop, PEL-based retry with exponential backoff, and dead-letter routing.
3. **Day 6–8:** Implement idempotent dedup table in PostgreSQL for billing notifications. Add `WAIT` to production of billing events.
4. **Day 9–10:** Wire monitoring — stream length, consumer lag, DLQ alert. Add on-call runbook for DLQ inspection and redelivery.
5. **Day 11–14:** Dark-launch with shadow reads from production traffic. Validate correctness, tune consumer pool sizing, cut over with a feature flag.

---

*Decision recorded 2026-07-06.*
