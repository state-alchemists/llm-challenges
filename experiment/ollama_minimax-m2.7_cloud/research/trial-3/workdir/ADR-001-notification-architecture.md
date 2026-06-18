# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

Our notification module currently sends emails and webhooks synchronously inside the HTTP request cycle. This has caused request timeouts (average 800ms, spikes to 8s at peak), silent failures with no retry, cascading failures from slow webhook endpoints exhausting connection pools, and no delivery guarantees for billing-critical notifications.

We need to decouple notifications from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), handle WebSocket push within 2 quarters, and absorb 10x traffic growth (500 req/s → 5,000 req/s peak). The team is 6 engineers, none with Kafka experience. We already run Redis for sessions and rate limiting. The 2-week setup constraint and modest budget rule out managed Confluent Cloud.

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams satisfies all our functional requirements at acceptable operational cost. It delivers per-stream ordering, consumer groups with acknowledgement-based retry, dead-letter handling, and sufficient throughput headroom — all without new infrastructure, specialized expertise, or a multi-week migration timeline.

## Consequences

### Benefits

- **Throughput**: Redis Streams sustains 100,000+ msg/s on commodity hardware. Our current 500 req/s (with 10x growth to 5,000 req/s) is well within capacity; even sustained burst patterns from task batch operations stay 1–2 orders of magnitude below the ceiling.
- **Ordering guarantee**: `XREADGROUP` delivers messages in stream order within each consumer group. This preserves the per-task ordering we need (e.g., task-created → task-updated → task-completed events must be processed in sequence).
- **Consumer groups and acknowledgements**: `XACK` enables acknowledgement-based delivery. Workers claim messages, process, then ack. On failure or timeout the message remains unacknowledged and can be reclaimed — providing at-least-once delivery without a custom timeout/retry layer.
- **Exactly-once for billing events**: Redis Streams alone cannot guarantee exactly-once (it is at-least-once). We close this gap by writing a deduplication table in our existing PostgreSQL database: each notification carries a deterministic idempotency key; before sending, the worker checks and inserts the key atomically using `INSERT ... ON CONFLICT DO NOTHING`. This is the same pattern used by Stripe and Twilio.
- **Dead-letter handling**: Messages that exceed a configurable retry count (e.g., 5 attempts) are moved to a dedicated `notifications.dlq` stream via `XADD`. A separate monitoring job alerts on DLQ depth, and operators can inspect/replay from the DLQ.
- **Operational continuity**: We already run Redis in production. No new binaries, no new infrastructure, no on-call unfamiliarity. The existing Redis instance (used for sessions and rate limiting) has headroom — we add a dedicated stream key namespace (`notifications:`) with its own memory budget and `MAXLEN` trimming policy.
- **Retry with exponential backoff**: Workers implement backoff using a `XCLAIM` with `MIN-IDLE-TIME` to re-steal messages that have been pending beyond a per-message retry budget. Combined with a `retry_count` header field in the message body, this is fully deterministic.
- **Timeline fit**: A working prototype is achievable in 2–3 days; production-ready migration in under 2 weeks. Libraries: `redis-py` (Python/Flask-compatible), `Streamified` (higher-level consumer group abstractions).

### Drawbacks

- **Message retention is memory-constrained**: Unlike Kafka's disk-backed log, Redis Streams stores messages in RAM. With high-throughput workloads and long retention windows, this can become expensive. Mitigation: enforce `MAXLEN` or `MAXLEN~` (approximate trimming) at the stream level. For our volume (~5,000 notifications/s peak × 86,400 s/day ≈ 432M entries/day before deduplication), we must ensure `MAXLEN` is set low enough that memory stays bounded. Recommended: 100,000–500,000 entries per stream with approximate trimming, which provides minutes of buffer at peak — sufficient for worker restarts.
- **Not a durable log by default**: Redis persistence (`RDB` + `AOF`) mitigates the risk, but Redis is not a write-ahead log like Kafka. If a replica fails and `AOF` is misconfigured, messages could be lost. Mitigation: ensure `AOF` is set to `everysec` or `always`, and consider replica nodes for read scalability.
- **Horizontal scaling ceiling**: Redis Streams scales horizontally via consumer groups, but a single stream can become a bottleneck at very high throughput (>100,000 msg/s sustained). For our 5,000 req/s target this is not a concern for the foreseeable future; however, if the platform grows to 100,000+ sustained notifications/s, a re-evaluation would be needed.
- **No native fan-out to multiple consumers**: A single message cannot be delivered to multiple independent consumer groups by default (unlike Kafka's multiple-consumer-group subscription model). For WebSocket push notifications, we will need a separate stream per notification class or a separate fan-out mechanism. This is a manageable architectural constraint, not a blocker.
- **Exactly-once requires application-layer dedup**: We rely on the PostgreSQL deduplication table for billing events. This is a well-understood pattern but adds a small synchronous DB round-trip per billing notification (sub-millisecond on local connection).

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for high-throughput event streaming and would handle our requirements trivially at any scale. It offers:

- Disk-backed durable log with configurable retention (hours to years) at no RAM cost.
- Exactly-once semantics via idempotent producers and transactional outbox patterns.
- Horizontal scalability to millions of msg/s with proper partitioning.
- Rich ecosystem: Kafka Connect, Confluent Schema Registry, ksqlDB.

**Why we rejected it:**

1. **Operational complexity**: Running Kafka (self-managed) requires ZooKeeper or KRaft configuration, topic and partition planning, replication factor settings, consumer group offset management, and JVM tuning. For a 6-person team with no Kafka experience and no dedicated infrastructure engineer, the on-boarding cost is 3–6 weeks before production confidence is achieved.
2. **Infrastructure cost**: Even self-managed on EC2, a minimal HA Kafka cluster (3 brokers + ZooKeeper) at production throughput requires at least 3 `m5.xlarge` instances, plus backup and monitoring. This exceeds our modest budget in compute alone.
3. **Two-week constraint**: Confluent Cloud would eliminate the operational burden but is cost-prohibitive at our scale; self-managed Kafka cannot be stood up and migrated in 2 weeks by an inexperienced team.
4. **Over-engineering**: Our throughput ceiling for the foreseeable future is ~5,000 notifications/s. Kafka is designed for orders-of-magnitude higher throughput. The flexibility is not yet warranted.

Kafka is the correct choice for a team that already runs it or plans to use it company-wide for event sourcing. We are not in that position today.

## Recommendation Summary

| Criterion | Redis Streams | Apache Kafka |
|-----------|---------------|--------------|
| Team familiarity | Already in production | No experience |
| Setup time | < 2 weeks | > 4 weeks |
| Operational burden | Low (shared Redis) | High (new cluster) |
| Peak throughput needed | 5,000 msg/s | 5,000 msg/s |
| Throughput ceiling | ~100,000 msg/s | Millions msg/s |
| Ordering guarantee | Per-stream | Per-partition |
| Exactly-once | App-layer dedup | Native (idempotent producer) |
| Message retention | RAM-bounded | Disk-backed, configurable |
| Infrastructure cost | Zero (uses existing) | 3+ EC2 instances minimum |
| WebSocket fan-out | Requires separate stream | Native multi-consumer-group |

Redis Streams is the pragmatic choice. It meets every stated requirement, leverages existing infrastructure, imposes no new operational burden, and can be production-ready in under two weeks. Kafka would be the correct long-term choice if the team grows, the platform reaches event-sourcing scale, or a company-wide event bus becomes part of the architecture — but not today.
