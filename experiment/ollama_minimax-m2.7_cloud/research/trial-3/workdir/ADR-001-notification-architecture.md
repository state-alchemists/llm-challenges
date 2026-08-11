# ADR-001: Notification Subsystem Architecture

## Status

**Proposed**

## Context

### The Problem

Our SaaS project management platform handles ~2M task events per month with a peak of ~500 req/s. The current notification module runs synchronously inside the HTTP request cycle, causing:

1. **Request timeouts** — Average latency 800ms, spiking to 8s during peak hours
2. **Silent failures** — No retry mechanism; downed email providers or webhook endpoints result in dropped notifications
3. **Cascading failures** — Two incidents where slow webhook endpoints exhausted connection pools, taking down unrelated features
4. **No delivery guarantees** — Billing-critical notifications ("trial expired", "payment failed") lack exactly-once semantics

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer, no Kafka experience
- **Existing infrastructure**: Redis already in production for sessions and rate limiting
- **Timebox**: Must deliver value within 2 weeks of migration work
- **Budget**: Modest; cannot afford managed Confluent Cloud at full scale
- **Scaling target**: Handle 10x traffic growth without re-architecting
- **Future requirements**: WebSocket push notifications within 2 quarters
- **Hard requirement**: Exactly-once semantics for billing notifications

### Technical Requirements

| Requirement | Detail |
|---|---|
| Throughput | 500 req/s peak, 10x growth target (~5,000 req/s) |
| Ordering | Per-user notification ordering preferred |
| Retention | At least 7 days for retry windows |
| Consumer groups | Multiple independent consumers (email, webhook, WebSocket) |
| Delivery semantics | At-least-once minimum, exactly-once for billing events |
| Retry policy | Exponential backoff with dead-letter handling |

---

## Decision

**Chosen option: Redis Streams**

Redis Streams is selected as the notification subsystem backbone, replacing the synchronous in-request notification flow.

### Justification

Given the team's size (6 people), lack of Kafka experience, 2-week delivery constraint, and existing Redis footprint, Redis Streams offers the best balance of capability, operational simplicity, and time-to-value.

| Factor | Redis Streams | Apache Kafka |
|---|---|---|
| **Team learning curve** | Low (team already knows Redis) | High (no Kafka experience) |
| **Operational burden** | Minimal (single Redis instance already running) | High (requires dedicated ops attention for broker config, partition management, schema registry) |
| **Setup time** | < 1 week | 2–4 weeks for production-ready cluster |
| **Infrastructure cost** | Existing instance sufficient; modest vertical scaling | Multi-broker cluster for resilience; managed option at full scale exceeds budget |
| **Throughput** | ~500k–1M msg/s on commodity hardware | Higher, but exceeds our 5,000 req/s ceiling by 2 orders of magnitude |
| **Message ordering** | Per-stream, per-consumer-group ordering | Per-partition ordering (requires careful key strategy) |
| **Exactly-once semantics** | Achieved via consumer-managed idempotency + stream position | Exactly-once via transactions (complex to configure) |
| **Multi-consumer support** | Consumer groups (like Kafka) | Native consumer groups |
| **Disk retention** | Configurable (default capped, can be unbounded) | Configurable retention |

The team's existing Redis expertise eliminates the Kafka learning curve entirely. Redis Streams provides the same consumer-group semantics as Kafka with a fraction of the operational complexity. The existing Redis cluster can be extended for stream storage without deploying new infrastructure.

---

## Consequences

### Pros of Redis Streams

1. **Fast implementation** — Team leverages existing Redis knowledge; POC can be running within days, production within the 2-week window.
2. **Operational simplicity** — No new systems to monitor, alert, or maintain beyond the Redis instance already in production.
3. **Cost-effective** — Uses existing infrastructure. No need for managed Kafka or multi-broker cluster.
4. **Sufficient throughput** — At ~500 req/s peak (targeting 5,000 req/s), Redis Streams comfortably handles the load. Kafka's higher throughput is unnecessary headroom for this scale.
5. **Consumer groups** — Native XREADGROUP supports multiple independent consumers (email worker, webhook worker, future WebSocket worker) sharing the same stream.
6. **Persistence and ordering** — Stream entries are persisted to AOF/RDB and maintain insertion order, satisfying retry and ordering requirements.
7. **Dead-letter via separate stream** — Failed messages (after max retries) can be routed to a dedicated `notifications.dlq` stream for manual inspection.

### Cons of Redis Streams

1. **No native exactly-once** — Redis Streams does not provide exactly-once delivery out of the box. Consumer-side idempotency (e.g., deduplication keys per notification ID) is required to achieve exactly-once for billing events. This is implementable but adds code complexity.
2. **Scaling ceiling** — At very high throughput (hundreds of thousands of messages per second), Redis Streams begins to show limitations. For a 10x growth target of ~5,000 req/s, this is not a concern.
3. **Ecosystem tooling** — Kafka has richer ecosystem tooling (Kafka Connect, Schema Registry, Streams API). Redis Streams is more minimal.
4. **Offset management** — Consumer group offset tracking is less mature than Kafka's; requires careful handling of `XPENDING` and `XACK`.
5. **No native replay from arbitrary time** — Kafka allows replay from any offset. Redis Streams allows replay from a given last-delivered ID, which is slightly less flexible.
6. **Operational knowledge gap at scale** — While Redis is familiar, stream-specific operations (XADD, XREADGROUP, XACK, XRANGE) may require new team knowledge.

---

## Alternatives Considered

### Apache Kafka

Kafka was rejected for the following reasons:

| Reason | Detail |
|---|---|
| **Learning curve** — | None of the 6 team members have Kafka experience. Topics, partitions, consumer groups, offset management, schema registry, and broker tuning represent significant new territory. |
| **Time to value** — | A production-ready Kafka deployment (multi-broker for resilience, partition strategy, consumer group setup, dead-letter handling, monitoring) typically takes 2–4 weeks. The 2-week constraint makes this high-risk. |
| **Operational complexity** — | Kafka requires careful tuning of retention, replication factor, and partition counts. Without a dedicated infrastructure engineer, the team would spend disproportionate time on operational toil. |
| **Cost** — | Self-managed Kafka requires a minimum of 3 brokers for resilience. Managed Confluent Cloud at relevant scale exceeds the modest budget. The existing Redis footprint is already paid for. |
| **Over-engineering** — | With a peak of 500 req/s (5,000 req/s target), Kafka's throughput capacity (millions of msg/s) is orders of magnitude beyond our requirement. The complexity-to-requirement ratio is unfavorable. |

Kafka remains a viable future choice if throughput requirements grow substantially beyond 10x or a dedicated platform team is added.

---

## Summary

| | Redis Streams | Apache Kafka |
|---|---|---|
| **Recommendation** | ✅ **Selected** | ❌ Rejected |
| **Team fit** | Existing Redis expertise | No Kafka experience |
| **Time to delivery** | < 2 weeks | 2–4+ weeks |
| **Operational burden** | Low | High |
| **Cost** | Existing infra | New multi-broker cluster |
| **Throughput fit** | Excellent (500–5,000 req/s) | Excessive (>1M msg/s capacity) |
| **Exactly-once** | Consumer-side idempotency required | Native with configuration |
| **Future WebSocket scaling** | Supports multi-consumer groups | Also supports |
