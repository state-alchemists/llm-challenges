# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

Our SaaS project management platform handles ~85,000 MAU and ~2M tasks/month, with a peak of ~500 req/s. The current notification system runs synchronously inside the HTTP request cycle, causing:

- **Request timeouts**: Average latency 800ms, spiking to 8s during peak hours.
- **Silent failures**: Dropped notifications with no retry when email providers or webhook endpoints are unavailable.
- **Cascading failures**: Two incidents where a slow webhook endpoint exhausted connection pools, affecting unrelated features.
- **No delivery guarantees**: Billing-critical notifications (trial expired, payment failed) lack exactly-once semantics.

The system must be decoupled, support retry with exponential backoff, guarantee at-least-once delivery for billing events, handle 10x traffic growth without re-architecture, and deliver WebSocket push within two quarters.

**Team constraints:**
- 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- No Kafka experience on the team.
- Redis already runs in production (sessions, rate limiting).
- Hard deadline: 2 weeks to setup/migration before delivering value.
- Budget: modest; cannot afford managed Confluent Cloud at full scale.

---

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams is the right fit given our constraints. It meets all functional requirements (ordering, retry, consumer groups, at-least-once with idempotent consumers), requires no new infrastructure or operational knowledge, and can be implemented within the 2-week deadline. Kafka's superior scalability and ecosystem are not yet warranted at our current load, and the team's unfamiliarity with Kafka would introduce unacceptable risk to the timeline.

---

## Consequences

### Pros of Redis Streams

| Property | Detail |
|---|---|
| **Operational simplicity** | Redis is already in production. No new servers, no new operational tooling, no new monitoring stack. |
| **Team familiarity** | The team already runs and debugs Redis daily. No learning curve for a critical piece of infrastructure. |
| **Fast delivery** | XREADGROUP, XACK, and XPENDING are a minimal API. An experienced Python developer can build a working consumer in hours. |
| **Ordering guarantees** | Redis Streams preserves insertion order within a consumer group, ensuring task-update → notification ordering is correct. |
| **Consumer groups** | XGROUP + XREADGROUP provides native fan-out to multiple consumers with cursor-based resumable consumption. |
| **Message retention** | Configurable retention (default infinite up to `maxlen`), suitable for our replay and debugging needs. |
| **At-least-once with idempotent consumers** | XDEL + application-level deduplication keys give exactly-once semantics for billing notifications. |
| **Throughput** | Redis Streams sustains ~500k–1M events/s on commodity hardware, far exceeding our ~500 req/s peak. |
| **No licensing or hosting cost** | Self-managed on existing infra; no Confluent Cloud bill. |
| **WebSocket roadmap** | Redis Pub/Sub can coexist with Streams for low-latency WebSocket push on the same infrastructure. |

### Cons of Redis Streams

| Property | Risk | Mitigation |
|---|---|---|
| **No native exactly-once** | Redis Streams lacks Kafka's transactional producer. | Application-level idempotency keys (dedupe on notification ID). |
| **Message retention is memory-bound** | Long-retention streams compete with Redis memory budget. | Stream trimming with `MAXLEN ~` or move to RDB snapshot archival for audit. |
| **No native dead-letter queue** | Failed messages after max retries need manual routing. | Implement a separate `notifications.dlq` stream as the DLQ; route via XRANGE inspection. |
| **No built-in schema registry** | Consumer schema evolution requires extra care. | Document notification payload schema; use versioning in the payload. |
| **Single-node persistence risk** | If the Redis primary fails, messages in flight are at risk (unlike Kafka's replicated logs). | Run Redis with AOF + RDB persistence; read replica for consumers. For 10x scale, promote to Redis Cluster. |
| **Less ecosystem tooling** | Kafka has Connect, Schema Registry, Streams KSQLDB. | Not needed at this scale. Custom Python scripts cover observability. |
| **Fan-out for multiple notification types** | If email + SMS + webhook each need独立 processing, Streams handles it but requires consumer group routing logic. | One consumer group per notification channel; straightforward to add. |

---

## Alternatives Considered

### Apache Kafka

| Property | Kafka | Redis Streams |
|---|---|---|
| **Setup time** | 2–4 weeks minimum (cluster provisioning, schema registry, consumer group design, team training) | 3–5 days (integrates with existing Redis) |
| **Operational complexity** | High: ZooKeeper/KRaft, partition balancing, replication tuning, connector management | Low: single Redis instance already operated |
| **Throughput** | ~1–10M events/s (far beyond our needs) | ~500k–1M events/s (headroom for 10x growth) |
| **Exactly-once semantics** | Native via transactional producer + consumer offset management | Requires application-level deduplication |
| **Message retention** | Log-compacted, configurable, disk-bound | Memory-bound (or AOF/RDB with retention limits) |
| **Consumer groups** | Native, mature, with partition rebalancing | XREADGROUP — functional equivalent, simpler model |
| **Team experience** | Zero; would require ramp-up and likely external consulting | Familiar; same Redis already in production |
| **Cost** | Managed Confluent Cloud at scale is expensive; self-managed requires dedicated infra | Zero incremental infra cost |
| **Ecosystem for future needs** | Kafka Connect, KSQLDB, Streams, Schema Registry — rich but overbuilt for this use case | Not applicable |

**Why Kafka was rejected:**

Kafka is the right tool for orders-of-magnitude higher throughput, multi-team event sourcing, or audit-critical workloads requiring hard exactly-once guarantees without application code. None of those conditions apply here:

1. **Current load is low**: 500 req/s peak with 10x headroom still fits comfortably in Redis Streams.
2. **Team has no Kafka experience**: The 2-week deadline makes Kafka setup and team ramp-up mutually exclusive.
3. **No dedicated infra engineer**: Running a Kafka cluster (self-managed) or managing Confluent Cloud configs requires specialized knowledge the team does not have.
4. **Cost at scale**: Confluent Cloud pricing for the throughput we need is unjustifiable on a modest budget. Self-managed Kafka on existing 4-web-server infra is operational overhead the team cannot absorb.

Kafka would be reconsidered if the platform scaled to millions of MAU, required event sourcing across multiple bounded contexts, or needed a unified event log that multiple downstream services consume independently.

---

## Summary

Redis Streams satisfies all stated requirements—async decoupling, retry with exponential backoff, at-least-once delivery with application-level exactly-once for billing, consumer group fan-out, and headroom for 10x growth—without requiring new infrastructure, new operational knowledge, or more than a few days of engineering time. Kafka's strengths (massive throughput, native exactly-once, rich ecosystem) are unnecessary at our scale and incompatible with our 2-week delivery constraint and team composition.
