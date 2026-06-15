# ADR-001: Notification Subsystem Message Broker

**Title:** Choose Redis Streams over Apache Kafka for the Notification Subsystem

**Status:** Proposed

**Date:** 2026-05-30

---

## Context

### The Problem

The notification module currently sends emails and webhooks synchronously inside the HTTP request cycle. As the platform has grown to ~85,000 MAU and ~2M tasks created per month, this synchronous approach has caused:

- **Request latency spikes**: Average notification latency is 800ms; peak hours see 8-second spikes because a slow email provider or webhook endpoint blocks the response.
- **Silent failures**: When an email provider or webhook endpoint is unavailable, notifications are dropped with no retry and no dead-letter queue.
- **Cascading failures**: Two incidents where a slow webhook endpoint exhausted the connection pool, destabilizing unrelated features.
- **No delivery guarantees**: Billing-critical notifications (trial expiration, payment failure) require exactly-once delivery, which the current system cannot provide.

### Constraints

| Constraint | Implication |
|------------|-------------|
| Team of 6 (3 senior, 3 mid-level) | No dedicated infrastructure engineer; operational overhead must be low |
| No Kafka experience on the team | Kafka requires significant ramp-up time |
| Already running Redis in production | Existing operational knowledge and infrastructure |
| 2-week maximum before delivering value | Cannot absorb a long migration or complex new system |
| Modest budget | Cannot afford Confluent Cloud or managed Kafka at full scale |
| Must preserve exactly-once for billing events | Non-negotiable requirement |

### Scaling Target

The chosen technology must support:
- Decoupled async processing (remove notifications from the HTTP request cycle)
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- WebSocket push notifications within 2 quarters
- 10x traffic growth without re-architecting (from ~500 req/s to ~5,000 req/s)

---

## Decision

**We choose Redis Streams.**

Redis Streams meets all functional requirements, integrates with existing infrastructure the team already operates, requires no new operational expertise, and can deliver value within the 2-week constraint.

---

## Technical Evaluation

### Apache Kafka

| Property | Value |
|----------|-------|
| **Throughput** | Excellent — sustained 100K–1M+ events/sec on commodity hardware |
| **Message retention** | Configurable, topic-level — days to indefinite |
| **Ordering guarantee** | Per partition — total order across a partition, none across partitions |
| **Consumer groups** | Native, first-class — rebalance on scale, offset management built-in |
| **Exactly-once semantics** | Transactional producers + idempotent consumers — strong guarantee but requires careful configuration |
| **Delivery guarantees** | At-least-once by default; exactly-once with `enable.idempotence=true` + transactions |

**Pros:**
- Battle-tested at massive scale (LinkedIn, Netflix, Uber scale)
- Native log-based retention allows replay and audit trails
- Consumer groups and partitions are designed for high-throughput parallel consumers
- Exactly-once via idempotent producers is well-documented
- Rich ecosystem: schema registry, Kafka Streams, ksqlDB, Connectors for external systems

**Cons:**
- **Operational complexity**: Requires managing brokers, ZooKeeper (or KRaft in newer versions), partition assignments, replication factor, and leader elections. Without a dedicated infra engineer, this is a significant burden.
- **Cluster sizing and partition strategy**: Getting partition counts and replication factor wrong causes hotspots and performance cliffes.
- **Client SDK complexity**: Python clients (confluent-kafka, kafka-python) require non-trivial configuration for idempotent producers and exactly-once consumption.
- **Ramp-up time**: The team has no Kafka experience. Expect 2–4 weeks to reach proficiency and 2+ weeks of implementation before delivering value.
- **Resource overhead**: Kafka needs dedicated brokers, at minimum 3 nodes for a production-safe setup. Not viable on existing Redis infrastructure.
- **Over-engineering for scale**: At 500 req/s (targeting 5,000 req/s), Kafka's throughput is orders of magnitude beyond what the system needs. The complexity premium is not justified at this scale.

### Redis Streams

| Property | Value |
|----------|-------|
| **Throughput** | Excellent for this tier — 50K–100K events/sec on a single Redis instance (well above our 5K req/s target) |
| **Message retention** | Configurable via `MAXLEN` (capped streams) or time-based `MAXLEN ~` trimming |
| **Ordering guarantee** | Total order within a single stream — all events for a consumer group are processed in insertion order |
| **Consumer groups** | Native `XREADGROUP` with `BLOCK` — supports multiple concurrent consumers, acknowledged delivery, and dead-letter tracking via `XPENDING` |
| **Exactly-once semantics** | Achieved via consumer-side idempotency (deduplication using notification ID as key in a Redis hash) — not built into the protocol but cleanly implementable |
| **Delivery guarantees** | At-least-once via `XREADGROUP` + `XACK`; exactly-once via idempotent consumer logic |

**Pros:**
- **Already in production**: The team has existing operational knowledge, monitoring, and runbooks for Redis. No new infrastructure to provision.
- **Low operational overhead**: Redis Streams is a first-class Redis data type. Single-node Redis handles our target load easily; replication provides HA if needed.
- **Familiar tooling**: `redis-py` and `rq-scheduler` integrate naturally with the existing Python/Flask codebase.
- **Consumer groups are first-class**: `XREADGROUP` with `BLOCK` provides non-blocking multi-consumer reads with automatic offset tracking, pending entry tracking (`XPENDING`), and consumer failure recovery.
- **Exactly-once achievable**: Consumer-side deduplication using a Redis hash keyed on the notification ID makes exactly-once delivery straightforward to implement and reason about.
- **Dead-letter tracking**: `XPENDING` reveals messages that have been delivered but not acknowledged, enabling retry with backoff. Failed messages can be moved to a dead-letter stream via `XRANGE` + `XADD`.
- **Can support WebSocket push**: A single Redis pub/sub channel or stream can fan out to multiple WebSocket servers, making real-time push achievable within the 2-quarter horizon.

**Cons:**
- **Not a durable log in the Kafka sense**: Redis Streams is an in-memory data structure with optional AOF persistence. While AOF provides durability, it is not a write-ahead log optimized for crash recovery the way Kafka's log-structured storage is.
- **Horizontal scale has limits**: A single Redis stream's throughput is bounded by a single Redis instance. At extreme scale (hundreds of thousands of events/sec), Redis Streams would need sharding (via Redis Cluster). For our 5,000 req/s target, this is not a near-term concern.
- **No native schema registry**: Events are opaque bytes; the producer and consumer must agree on format out-of-band.
- **Smaller ecosystem**: Fewer off-the-shelf connectors and tools compared to Kafka.

---

## Consequences

### Positive

- **Faster time-to-value**: The team can implement and deploy a working notification queue within days, using existing Redis infrastructure and Python libraries they already know.
- **Operational simplicity**: Redis Streams requires no new services, no new runbooks, and no new operational expertise. The team manages Redis today; they will continue to manage it in the same way.
- **Exactly-once for billing**: Consumer-side deduplication via a Redis hash (keyed on notification ID) provides a clean, auditable exactly-once guarantee. Combined with `XACK`, failures are recoverable without duplicate delivery.
- **Retry with backoff**: `XPENDING` tracks unacknowledged messages; a consumer can replay them with exponential backoff by re-reading pending entries after a configurable timeout.
- **Future WebSocket support**: Redis pub/sub can fan out to multiple WebSocket servers, making real-time push a natural extension rather than a future migration.
- **Cost-effective**: No new infrastructure required; Redis handles this load on the existing deployment.

### Negative

- **Not a durable event log**: AOF persistence is less robust than Kafka's log-structured storage. For audit-critical replay of historical events, Redis Streams is less suitable. However, the notification use case does not require multi-day replay — retries within hours are sufficient.
- **Single-stream bottleneck at extreme scale**: If the platform grows to 10x beyond the 10x target (50K+ req/s), Redis Streams would require sharding. This is not a near-term concern given current projections.
- **No native schema enforcement**: Teams must document notification event schemas and enforce compatibility at the application layer, not the broker layer.
- **Operational limits**: If Redis itself has an incident, the notification pipeline pauses. Redis HA (Redis Sentinel or Cluster) mitigates this, but it is additional configuration.

---

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard choice for high-throughput event streaming and would comfortably handle the notification workload. However:

1. **No existing expertise**: The team has no Kafka experience. The 2-week constraint would be violated — a realistic estimate for the team to reach proficiency and deliver a working implementation is 4–6 weeks.
2. **No operational infrastructure**: Kafka requires 3+ brokers, ZooKeeper or KRaft, and careful partition/replication configuration. The team has no one with this expertise and no budget for managed Confluent Cloud.
3. **Over-engineered for the problem**: At 500–5,000 req/s, Kafka's throughput is 100–1,000x beyond what the system needs. The complexity premium is disproportionate.
4. **New infrastructure required**: Kafka cannot reuse the existing Redis deployment; it requires dedicated nodes.

**Verdict:** Kafka is the right tool for a company that is already built around event streaming, has dedicated infrastructure engineers, and is operating at LinkedIn scale. For a 6-person team running a Flask monolith with existing Redis infrastructure, it is the wrong tool.

### Keep Synchronous (No Change)

The current synchronous approach has already caused cascading failures and silent data loss. This is not a viable path forward.

**Verdict:** Rejected — does not address any of the stated problems.

---

## Recommendation

**Redis Streams** is the correct choice given the constraints:

- The team already operates Redis; no new infrastructure, no new operational expertise required.
- Consumer groups (`XREADGROUP`) provide all necessary primitives: at-least-once delivery, pending message tracking, multi-consumer parallel processing, and consumer failure recovery.
- Exactly-once is achievable via consumer-side idempotency (notification ID deduplication in a Redis hash) — simpler and more auditable than Kafka's exactly-once configuration.
- Redis pub/sub provides the foundation for the WebSocket push notifications planned within 2 quarters.
- A working implementation is achievable within the 2-week constraint using existing Python libraries.

If at some future point the platform exceeds ~50,000 req/s or requires multi-day event replay for audit purposes, Kafka becomes the more appropriate tool. At that point, the team will have the operational maturity and potentially the headcount to manage it properly. Until then, Redis Streams is the right tool for this team at this scale.