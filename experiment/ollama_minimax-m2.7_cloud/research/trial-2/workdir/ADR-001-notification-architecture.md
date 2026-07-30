# ADR-001: Notification Subsystem Message Broker Selection

## Status

**Proposed**

## Context

The current notification module executes synchronously within the HTTP request cycle, causing:
- Average response latency of 800ms, spiking to 8s during peak hours
- Silent notification failures when email providers or webhook endpoints are unavailable
- Cascading failures that exhausted connection pools and disrupted unrelated features
- No delivery guarantees for billing-critical notifications (trial expiry, payment failures)

**System constraints:**
- 85,000 MAU, ~2M tasks/month, peak 500 req/s
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience; Redis already in production for sessions and rate limiting
- 2-week maximum migration window before delivering value
- Modest budget; cannot afford managed Confluent Cloud at scale
- Must guarantee exactly-once delivery for billing events

**Scaling targets:**
- Async processing decoupled from HTTP requests
- Retry with exponential backoff
- 10x traffic growth without re-architecting
- WebSocket push notifications within 2 quarters

## Decision

**Chosen option: Redis Streams**

Redis Streams is selected as the message broker for the notification subsystem.

**Justification:**

Given the team's familiarity with Redis, the existing production infrastructure, the 2-week delivery constraint, and the modest budget, Redis Streams provides the best balance of capability, operational simplicity, and time-to-value.

| Criterion | Kafka | Redis Streams | Verdict |
|-----------|-------|---------------|---------|
| **Throughput** | Millions/sec | 100K–500K/sec | Redis adequate (500 req/s current, 10x = 5K req/s) |
| **Ordering** | Per-partition | Per-stream (XADD order) | Equivalent for single-partition workloads |
| **Message retention** | Hours to weeks (configurable) | Up to ~512MB per stream (MAXLEN) | Redis adequate for notification volumes |
| **Consumer groups** | Yes (mature) | Yes (XREADGROUP, XACK) | Equivalent capability |
| **Exactly-once** | Native (transactions API) | At-least-once + application dedup | Kafka wins on paper, but both require app-level work |
| **Ops complexity** | High (cluster setup, replication, monitoring) | Low (already running) | Redis dramatically lower |
| **Learning curve** | Steep (no team experience) | Minimal (existing Redis knowledge) | Redis advantage |
| **Setup time** | 2–4 weeks minimum | 3–5 days | Redis meets constraint; Kafka does not |
| **Infrastructure cost** | Full cluster (3+ brokers minimum for HA) | Leverages existing instance | Redis minimal incremental cost |
| **Self-hosting risk** | High (no infra engineer) | Low (team knows Redis) | Redis lower risk |

The billing exactly-once requirement can be met in Redis Streams using an idempotency key pattern: each billing event carries a unique `event_id`, and consumers maintain a short-lived deduplication window (e.g., Redis SET with TTL) before processing. This is a well-established pattern that adds negligible overhead.

## Consequences

### Pros of Redis Streams

1. **Operational continuity**: Team manages existing Redis; no new infrastructure to operate.
2. **Fast onboarding**: Redis expertise transfers directly; no external training needed.
3. **Rapid delivery**: Proof-of-concept achievable in days; full migration within 2 weeks.
4. **Cost efficiency**: No additional managed services; leverages existing investment.
5. **Sufficient scale**: 500 req/s current → 5,000 req/s at 10x easily fits within Redis Streams' practical throughput (100K–500K/sec under realistic workloads).
6. **Consumer groups**: XREADGROUP provides competing consumer semantics, enabling multiple workers to process notifications in parallel with at-least-once guarantees.
7. **Persistence**: Redis RDB/AOF provides durability; streams append to the log.
8. **Blocking reads**: XREAD with BLOCK enables efficient event polling without busy-waiting.

### Cons of Redis Streams

1. **Exactly-once requires application code**: Unlike Kafka's transactions API, Redis Streams provides at-least-once delivery; application must implement deduplication using idempotency keys. (Effort: ~1–2 days to implement correctly.)
2. **Memory-bound retention**: Streams cap at ~512MB per stream; long retention windows require trimming (MAXLEN). For notification use cases (hours to days retention), this is not a constraint.
3. **No native compaction**: Kafka's log compaction is more flexible for event sourcing. Not required for this notification use case.
4. **Fan-out limitations**: Single-stream fan-out to multiple consumer groups requires explicit XREADGROUP from each group; Kafka's consumer groups handle this more elegantly. Mitigation: separate streams per notification type if needed.
5. **Monitoring maturity**: Redis Streams monitoring (via Redis INFO, Redis Exporter) is less mature than Kafka's ecosystem (Kafka Manager, Confluent Control Center). Mitigation: standard Redis metrics + custom instrumentation.

### Pros of Kafka (for reference)

1. **Native exactly-once semantics**: Kafka transactions eliminate the need for application-level deduplication.
2. **Massive throughput**: 1M+ events/sec per broker—useful if traffic grows 100x.
3. **Mature ecosystem**: Consumer groups, schema registry, Kafka Streams, Connectors.
4. **Log compaction**: Supports arbitrary replay and event sourcing patterns.
5. **Multi-tenancy**: Better isolation for large-scale multi-tenant SaaS.

### Cons of Kafka (for reference)

1. **Operational burden**: 3+ broker cluster minimum for HA; requires ZooKeeper or KRaft, partition balancing, replication tuning.
2. **Steep learning curve**: No team experience; estimated 4–6 weeks to reach proficiency.
3. **Exceeds 2-week constraint**: Infrastructure provisioning, configuration, and team ramp-up cannot meet the deadline.
4. **Infrastructure cost**: 3-broker HA cluster adds significant compute cost; cannot afford Confluent Cloud managed tier.

## Alternatives Considered

### Apache Kafka

Kafka was evaluated as the gold-standard solution for event streaming workloads. Its native exactly-once semantics, million-event throughput, and mature ecosystem make it the default choice for high-scale distributed systems.

**Why it was rejected:**

1. **Timeline violation**: Building a 3-broker HA Kafka cluster, configuring replication, training the team, and migrating the notification module cannot be completed within 2 weeks. The constraint explicitly forbids solutions that delay value delivery.
2. **Operational expertise gap**: The team has no Kafka experience and no dedicated infrastructure engineer. Kafka's operational surface area—partition leadership, ISR (in-sync replica) management, consumer lag monitoring, schema evolution—is significantly larger than Redis. Running Kafka in production without this expertise introduces unacceptable risk.
3. **Budget incompatibility**: Managed Kafka (Confluent Cloud, Amazon MSK) at production scale exceeds the modest budget. Self-hosted Kafka requires 3+ dedicated hosts with proper network configuration, adding EC2 cost.
4. **Over-engineering**: Current throughput is 500 req/s; 10x growth is 5,000 req/s. Redis Streams comfortably handles this. Kafka's million-event throughput is 200x excess capacity for this use case.

Kafka remains a viable future option if the team grows an infrastructure engineer, traffic exceeds 50,000 req/s, or the product evolves toward event sourcing.

---

## Recommendations

1. **Immediate (Week 1)**: Implement Redis Streams producer in Flask, push notification events asynchronously via background thread/process. Existing sync path remains until new path is validated.
2. **Week 2**: Implement consumer groups with XREADGROUP, exponential backoff retry logic (using XACK + re-XADD on failure), and idempotency-key deduplication for billing events.
3. **Monitoring**: Instrument consumer lag via Redis Streams `XLEN` and custom metrics (events processed, failed, retried).
4. **Future (if needed)**: If throughput exceeds 50,000 req/s or event sourcing becomes a requirement, evaluate Kafka as a migration target.
