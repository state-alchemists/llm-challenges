# ADR-001: Notification Subsystem Architecture

## Status

**Proposed**

## Context

### Problem Statement

We run a SaaS project management platform with:
- **85,000 monthly active users**
- **~2 million tasks created per month**
- **Peak load: ~500 req/s**

The current notification module (emails and webhooks on task events) runs **synchronously inside the HTTP request cycle**, causing:

1. **Request timeouts** — Average latency 800ms, spikes to 8s during peak hours
2. **Silent failures** — No retry, no dead-letter queue; notifications dropped when email providers or webhook endpoints are down
3. **Cascading failures** — Two incidents where slow webhook endpoints caused connection pool exhaustion, taking down unrelated features
4. **No delivery guarantees** — Billing-critical notifications (trial expired, payment failed) have no exactly-once guarantee

### Scaling Target

The system must:
- Decouple notifications from the HTTP request cycle (async processing)
- Support retry with exponential backoff
- Guarantee **at-least-once delivery** for billing events; **exactly-once** where feasible
- Add real-time WebSocket push notifications within 2 quarters
- Handle **10x traffic growth** without re-architecting

### Constraints

| Constraint | Implication |
|---|---|
| Team: 6 engineers (3 senior, 3 mid-level) | No dedicated infrastructure engineer; everyone wears multiple hats |
| No Kafka experience on the team | Kafka has a steep learning curve that costs sprint velocity |
| Redis already in production | Session storage and rate limiting already use Redis |
| 2-week maximum setup/migration | Must deliver value quickly; cannot spend months on infrastructure |
| Modest budget | Cannot afford Confluent Cloud at full scale; self-managed is the path |
| Exactly-once for billing notifications | Non-negotiable requirement for billing events |

---

## Decision

**We will use Redis Streams as the notification subsystem's message broker.**

### Justification

Given the team's size (6 people), existing Redis expertise, and the 2-week delivery constraint, Redis Streams provides the fastest path to a production-grade async notification system without the operational overhead of Kafka.

The critical factors in this decision:

1. **Operational familiarity** — The team already operates Redis in production for session storage and rate limiting. No new infrastructure to learn, monitor, or debug at 2am.

2. **Speed to value** — Redis Streams requires no separate cluster setup beyond what already exists. The team can be productive within days, not weeks.

3. **Sufficient throughput** — At peak 500 req/s with potential 10x growth to ~5,000 req/s, Redis Streams handles **100,000–1,000,000 events/second** on commodity hardware — more than adequate headroom.

4. **Ordering guarantees** — Redis Streams guarantees ordering per consumer group, which satisfies our requirement for FIFO notification delivery within a given notification type.

5. **Consumer groups** — Redis Streams consumer groups provide competing consumer semantics, enabling horizontal scaling of notification workers with automatic load distribution and claim management for failed deliveries.

6. **Message retention** — Configurable via `MAXLEN` or `MINID`, allowing retention of events for replay or debugging without unbounded storage growth.

7. **Exactly-once for billing** — Redis Streams + idempotent consumer logic (tracking processed event IDs in a Redis SET) delivers exactly-once semantics for billing-critical notifications. The pattern is: read stream entry → check processed set → if not seen, process and add ID to processed set.

---

## Consequences

### Pros of Redis Streams

| Property | Detail |
|---|---|
| **Operational simplicity** | Single Redis instance already maintained; no new service to operate |
| **Low latency** | Sub-millisecond latency for enqueue/dequeue operations |
| **Horizontal scaling** | Add consumers to a consumer group to scale throughput |
| **Persistence** | Redis RDB/AOF provides durability; streams survive Redis restarts |
| **Replay capability** | Streams can be read from any offset, enabling backfill and debugging |
| **No additional cost** | Uses existing Redis infrastructure; no new licensing or hosting fees |
| **Familiar programming model** | Consumer groups are similar to Kafka consumer groups; transferable concepts |
| **WebSocket roadmap** | Redis Pub/Sub can complement streams for the real-time WebSocket layer |

### Cons of Redis Streams

| Issue | Mitigation |
|---|---|
| **No native dead-letter queue** | Implement a separate stream (`notifications.dlq`) for failed messages after max retries; monitor DLQ depth |
| **Single-point-of-failure if Redis goes down** | Run Redis in **Redis Sentinel** or **Redis Cluster** mode for HA; Sentinel is already a common pattern |
| **Memory-bound scaling** | Stream entries consume memory; set appropriate `MAXLEN` policies and prune aggressively |
| **Less mature monitoring ecosystem** | Use Redis `STREAM INFO`, `CLIENT LIST`, and Prometheus exporters; fewer turnkey solutions than Kafka |
| **No native cross-datacenter replication** | Redis Cluster or Sentinel cross-AZ replication requires careful configuration |
| **Fan-out complexity for multi-channel** | If the same event must go to email + webhook + SMS, use stream consumer groups per channel or a branching worker |

### Operational Trade-offs

- **Redis Sentinel** (minimum 3 nodes) is required for HA — adds complexity but is well-documented
- Stream consumer groups require careful offset management; use `XREADGROUP BLOCK` with `LASTDELIVERED` tracking
- Monitoring DLQ depth and stream length requires custom dashboards (Prometheus + Grafana recommended)

---

## Alternatives Considered

### Apache Kafka

| Property | Kafka | Redis Streams | Verdict |
|---|---|---|---|
| **Throughput** | Millions/sec | 100k–1M/sec | Kafka wins, but overkill for 500 req/s (10x growth = 5,000 req/s) |
| **Operational complexity** | High (broker config, partition management, replication tuning, ZooKeeper/KRaft) | Low (existing Redis skill set) | Redis Streams clear winner |
| **Learning curve** | Steep (no team experience) | Minimal (team uses Redis daily) | Redis Streams clear winner |
| **Setup time** | 2–4 weeks minimum for production-ready cluster | 3–5 days | Redis Streams required for 2-week constraint |
| **Exactly-once semantics** | Native Kafka Transactions API | Consumer-side idempotency (event ID dedup in Redis SET) | Kafka wins on paper, but Redis pattern is sufficient for billing events |
| **Message retention** | Days/weeks/months, log-compacted | Limited by `MAXLEN` or `MINID`; memory-bounded | Kafka wins for event sourcing |
| **Ecosystem tooling** | MirrorMaker, Confluent Schema Registry, Connect, Streams | `redis-cli`, Redisinsight, Prometheus exporter | Kafka has richer tooling but higher operational cost |
| **Team readiness** | No Kafka experience; would require training and 2 on-call runbooks | Existing Redis expertise; one runbook | Redis Streams |

### Why Kafka Was Rejected

1. **No team experience** — Kafka has a steep operational learning curve. Misconfigured retention, incorrect partition counts, or broker failures would require expertise the team does not have.

2. **2-week constraint is not achievable** — A production-ready Kafka deployment with proper replication, monitoring, alerting, and runbooks requires 2–4 weeks minimum. We cannot meet the delivery timeline.

3. **Cost and infrastructure** — Even a minimal HA Kafka cluster (3 brokers + ZooKeeper/KRaft) requires significantly more resources than a Redis Sentinel HA setup.

4. **Over-engineering** — Our throughput ceiling is ~5,000 req/s after 10x growth. Kafka is architected for millions of events per second at internet scale. The added complexity is not justified by our requirements.

5. **Existing Redis investment** — We already rely on Redis. Leveraging it for streams is incremental; Kafka would be net-new infrastructure in its entirety.

---

## Recommendation

**Proceed with Redis Streams.** The team already operates Redis, the 2-week constraint is achievable, and the throughput requirements are well within Redis Streams' capacity. The exactly-once requirement for billing notifications is implementable via idempotent consumers using Redis SET for event ID deduplication.

The architecture pattern:

1. Flask endpoints **enqueue** notification events to a Redis Stream (`notifications.outbound`)
2. Worker processes (consumer group: `notification-workers`) **dequeue** via `XREADGROUP`
3. Workers dispatch to email providers or webhook endpoints with exponential backoff retry
4. After max retries, events route to a **dead-letter stream** (`notifications.dlq`)
5. Billing events use **idempotent processing**: event ID stored in a Redis SET (`notifications.processed`) with a TTL; duplicates are discarded

This delivers immediate value within the 2-week window while leaving headroom for the WebSocket push notification feature in the next two quarters.
