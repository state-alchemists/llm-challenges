# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

The current notification module executes synchronously inside the HTTP request cycle, causing:
- **Request timeouts** (average 800ms, spikes to 8s at peak)
- **Silent failures** with no retry or dead-letter queue
- **Cascading failures** from slow webhook endpoints exhausting connection pools
- **No delivery guarantees** for billing-critical notifications

**System scale:** 85,000 MAU, ~2M tasks/month, 500 req/s peak, 10x growth target within scope.

**Constraints:**
- Team: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience on the team
- Redis already running in production (session storage, rate limiting)
- Maximum 2-week setup/migration before delivering value
- Modest budget (cannot afford managed Confluent Cloud)
- Exactly-once semantics required for billing notifications

## Decision

**Choose Redis Streams.**

Redis Streams is the correct choice given the team's constraints. It meets all functional requirements, leverages existing infrastructure, imposes minimal operational overhead, and can be implemented within the 2-week deadline.

### Technical Justification

**Throughput:**  
Redis Streams easily handles 500 req/s and the 10x growth target (5,000 req/s). Each task event is a small JSON payload (<1KB); Redis Streams on a standard AWS Redis instance (e.g., cache.r6g.medium) sustains tens of thousands of ops/sec. Kafka would be architecturally overengineered for this load profile.

**Ordering Guarantees:**  
Redis Streams guarantees **per-consumer-group ordering** within a single stream. Messages are delivered in insertion order (XRANGE). This is sufficient for our use case: notifications for a given task must be processed in order, which Redis Streams provides. Kafka provides stronger total ordering across partitions, but that property is not required here.

**Message Retention:**  
Redis Streams retains messages until explicitly trimmed (`XTRIM`, `MAXLEN`). Default behavior retains all messages until you set a retention policy. For the notification use case, a 7-day retention window is typical and configurable with `MAXLEN ~ 100000` or time-based via `MINID`. This is functionally adequate.

**Consumer Groups (Exactly-Once via At-Least-Once + Deduplication):**  
Redis Streams consumer groups (`XREADGROUP`, `XACK`) provide **at-least-once delivery**. For billing notifications requiring exactly-once semantics, the idempotency is achieved at the application layer:
- Producer emits a notification with a deterministic UUID derived from `billing_event_id + notification_type`
- Consumer checks a Redis SET (or PostgreSQL row) for the UUID before processing
- On successful processing, write the UUID with a TTL (e.g., 24h)
- On retry, the duplicate is detected and silently acknowledged

This pattern is well-understood and straightforward to implement in Python/Flask.

**Retry with Exponential Backoff:**  
Implement via a **retry stream** or dead-letter stream pattern:
1. Consumer fails to deliver → write message to a `notifications.retry` stream with a future timestamp
2. A retry worker reads from `notifications.retry` using `XRANGE` with timestamps, republishes to the main stream after the backoff interval
3. After N retries (configurable, e.g., 5), move to `notifications.dlq` for manual inspection

This is fully implementable with existing Redis commands and Python.

**Consumer Groups and Scalability:**  
`XREADGROUP` supports multiple concurrent consumers within a consumer group. Redis automatically distributes messages, providing horizontal scalability. Add workers by spawning more consumer processes; no reconfiguration required.

**Operational Complexity:**  
Redis Streams requires **no new infrastructure**. The team manages it with existing Redis expertise. No new monitoring pipelines, no Kafka Connect, no schema registry, no JVM tuning. For a 6-person team with no dedicated infrastructure engineer, this operational simplicity is decisive.

**Setup Time:**  
A working prototype can be running in 2–3 days using `redis-py` and Python threading/multiprocessing. Migration of the existing notification path can be done incrementally (add a Redis Streams producer alongside the existing sync path, validate, then cut over). This comfortably fits within the 2-week constraint.

## Consequences

### Positive

- **No new infrastructure** — reuses existing Redis, no procurement or configuration cycles
- **Team already knows Redis** — no training ramp-up, no unfamiliar concepts
- **Fast implementation** — prototype in days, production migration in under 2 weeks
- **Operational simplicity** — standard Redis monitoring (已有的 Redis哨兵/Armory dashboards), no new alerting systems
- **At-least-once with idempotency** — billing notification exactly-once achievable at the application layer
- **Scalable to 10x** — 5,000 req/s is well within Redis Streams' capability on appropriately sized instances
- **Supports WebSocket push** — a WebSocket worker can subscribe to the stream alongside email/webhook workers, enabling the real-time push requirement within the existing architecture

### Negative

- **Single-node Redis as bottleneck** — if the Redis instance becomes the bottleneck (unlikely at 5K req/s for notification payloads, but possible under extreme growth), you need Redis Cluster. Redis Streams on Cluster has limitations (stream keys must be hash-slotted, no native cross-slot operations). Mitigation: size the Redis instance appropriately (use AWS ElastiCache or MemoryDB with sufficient memory and network bandwidth); plan for Redis Cluster migration if 10x growth materializes beyond 18 months.
- **No native replay from offset** — Kafka allows rewinding a consumer group to any offset. Redis Streams allows replay within the window (`XRANGE`), but this is bounded by retention. For most debugging/replay scenarios this is sufficient, but audit replay beyond the retention window requires a separate archive (e.g., dump to S3 periodically).
- **No native dead-letter queue** — implemented manually as a separate stream (`notifications.dlq`). Adds a small amount of custom code.
- **Not a universal log** — Redis Streams is not designed as a general-purpose event log for analytics. If the business later needs event sourcing or analytics on notification events, this pattern may need to be augmented (e.g., with PostgreSQL changelog or a dedicated analytics pipeline). For the current notification use case, this is not a concern.
- **Exactly-once requires application-level work** — unlike Kafka Transactions (which provide exactly-once end-to-end), Redis Streams requires the deduplication pattern described above. This is standard practice but adds a small amount of application logic.

## Alternatives Considered

### Apache Kafka

**Why rejected:**

1. **No team experience.** Kafka has a steep operational learning curve: topic partitioning, replication factor, consumer group offsets, retention sizing, log compaction, JVM tuning (for self-managed), schema registry for Avro/Protobuf. A 6-person team with no dedicated infrastructure engineer will spend the first 2 weeks learning, not delivering value.

2. **Exceeds setup time constraint.** Even with a managed offering (AWS MSK, Confluent Cloud), the team needs time to design topic schemas, configure consumer groups, set up monitoring, and build operational runbooks. 2 weeks is insufficient to go from zero to production-ready for a team that has never operated Kafka.

3. **Budget risk.** Self-managed Kafka on EC2 requires significant operational overhead (cluster sizing, replication, upgrades, monitoring). Confluent Cloud or AWS MSK at production scale (5,000 req/s × payload size × replication factor) carries costs that exceed a modest budget. Redis Streams runs on the existing Redis cluster at no additional infrastructure cost.

4. **Overengineered for the workload.** Kafka excels at millions of events per second across many producers and consumers with complex fan-out. Our workload is 500 req/s with a small number of consumer types (email, webhook, WebSocket). The architectural gap between "fits Redis Streams" and "needs Kafka" is substantial, and we are firmly on the Redis Streams side.

5. **Exactly-once is not free in Kafka either.** While Kafka provides exactly-once semantics via transactions, using it correctly requires careful configuration and still needs idempotency at the consumer for truly end-to-end exactly-once (e.g., against a database). The advantage is smaller than it appears.

**When Kafka would be correct:** If the notification volume exceeded ~50,000 events/second, or if there were dozens of independent consumer services with complex event routing, or if the team had an existing Kafka cluster and expertise — then Kafka would be the clear choice. None of those conditions apply here.

---

## Summary

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| Team familiarity | High (existing Redis) | Low (no experience) |
| Setup time | < 2 weeks | > 2 weeks (learning curve) |
| Infrastructure cost | Zero (existing Redis) | Significant (new infra or managed service) |
| Throughput capacity | 10x+ growth target | Exceeds requirements |
| Ordering guarantee | Per-stream (sufficient) | Total ordering (overkill) |
| Exactly-once | Application-layer idempotency | Kafka Transactions (complex) |
| Operational complexity | Low | High |
| WebSocket push support | Native (XREAD on same stream) | Requires separate consumer |

**Recommendation:** Implement the notification subsystem using Redis Streams with the pattern described in this ADR. Begin with a single `notifications` stream, consumer groups for email/webhook/WebSocket workers, application-level idempotency for billing events, and a manual DLQ stream. Re-evaluate Redis Cluster if and when 10x growth materializes beyond the first year.
