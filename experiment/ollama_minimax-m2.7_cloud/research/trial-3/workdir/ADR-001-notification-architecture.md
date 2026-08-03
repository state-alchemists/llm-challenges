# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

### Problem Statement

The notification module sends emails and webhooks synchronously inside the HTTP request cycle. This causes:

- **Request timeouts**: Average latency 800 ms, spikes to 8 s during peak hours.
- **Silent failures**: If an email provider or webhook endpoint is down, the notification is dropped with no retry or dead-letter queue.
- **Cascading failures**: A slow webhook endpoint caused connection pool exhaustion and took down unrelated features twice this year.
- **No delivery guarantees**: Billing-critical notifications ("trial expired", "payment failed") have no exactly-once guarantee.

### Scaling Requirements

- Decouple notifications from the HTTP request cycle (async processing).
- Retry with exponential backoff.
- At-least-once delivery for billing events; exactly-once where feasible.
- Real-time WebSocket push notifications within 2 quarters.
- Handle 10× traffic growth without re-architecting.

### System Scale

| Metric | Value |
|---|---|
| Monthly active users | 85,000 |
| Tasks created/month | ~2,000,000 |
| Peak request rate | ~500 req/s |
| Target throughput (10×) | ~5,000 events/s |

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Operational experience**: Redis already in production (session storage, rate limiting). No Kafka experience.
- **Timeline**: Must deliver value within 2 weeks of starting work.
- **Budget**: Cannot afford managed Confluent Cloud at full scale.
- **Billing semantics**: Exactly-once delivery is a hard requirement for billing notifications.

---

## Decision

**Chosen option: Redis Streams**

Redis Streams is selected as the message broker for the notification subsystem.

### Justification

The team's existing Redis footprint is the primary driver. Redis Streams requires no new infrastructure, no new operational expertise, and no additional hosting cost beyond what is already budgeted. The 2-week constraint rules out any option that requires meaningful new operational knowledge or provisioning; Redis Streams satisfies this because the team already operates Redis in production.

At a throughput of ~5,000 events/s (10× the current peak), Redis Streams comfortably exceeds requirements. Redis is benchmarked at 100,000–200,000 events/s on commodity AWS instances for simple workloads like this. Ordering within a stream is guaranteed per consumer group, which is sufficient for notification correctness.

The exact-once requirement for billing events is achievable: Redis Streams 5.0+ supports consumer-group acknowledgement, and applying a deduplication layer (storing processed message IDs in a Redis hash with a TTL) closes the gap to exactly-once at the application level. This is a well-established pattern with lower operational overhead than Kafka's transaction-based exactly-once semantics.

---

## Consequences

### Benefits of Redis Streams

1. **No new infrastructure**: Runs on the existing Redis 7.x instance already deployed. No brokers, no ZooKeeper, no KRaft controllers to manage.
2. **Fast onboarding**: The team reads and writes Redis data structures already. Streams syntax (`XADD`, `XREADGROUP`, `XACK`) is learnable in hours.
3. **Operational simplicity**: Redis Streams requires no schema registry, no partition rebalancing procedures, and no special monitoring tooling beyond what Redis already exposes (`INFO streams`, `XLEN`, lag metrics via `XPENDING`).
4. **Adequate throughput**: ~100,000–200,000 events/s on a single Redis instance is more than the 10× scaling target requires. Multiple consumer groups allow horizontal scaling of workers.
5. **Message retention**: Configurable up to 2^64−1 bytes. A notification stream with 30-day retention (sufficient for replay and debugging) is trivially affordable on Redis RDB/AOF persistence.
6. **Exactly-once via deduplication**: Storing a hash of `message_id → processed` with a TTL achieves application-level exactly-once. This is simpler to reason about and debug than Kafka's exactly-once semantics for a team with no Kafka experience.
7. **WebSocket readiness**: Redis pub/sub or Streams can fan out to WebSocket workers without architectural change. This aligns with the 2-quarter roadmap item.
8. **Cost**: Zero incremental infrastructure cost.

### Drawbacks of Redis Streams

1. **No native partition broadcasting**: A single stream is ordered per consumer group. Multiple independent workers reading the same stream get disjoint subsets (via `XREADGROUP`). This is sufficient for notification dispatch but differs from Kafka's fan-out model where all consumers receive all messages in a topic partition.
2. **Message retention trade-off**: Redis is primarily an in-memory store. With 30-day retention and high-volume notification traffic, memory usage must be monitored and `maxmemory-policy` configured appropriately. Under very heavy load (sustained 50,000+ events/s), this becomes a cost/performance consideration that Kafka does not have.
3. **No native dead-letter queue**: Dead-letter handling must be built as a separate stream (e.g., `notifications.dlq`) and consumer group, or handled via a separate retry stream with a TTL. Kafka has richer dead-letter routing built-in.
4. **Smaller ecosystem**: Monitoring integrations, connectors, and tooling are less mature than Kafka's ecosystem. The team must instrument more manually (e.g., Prometheus metrics for lag, pending counts).
5. **At-most-once risk if misused**: If a worker crashes after `XREAD` but before `XACK`, the message is reprocessed. This is addressed by the deduplication layer but adds application-level complexity.
6. **Single Redis instance is a single point of failure**: If the Redis instance goes down, the notification pipeline stops. Redis Cluster can mitigate this but adds operational complexity that may exceed the 2-week constraint. A single Redis instance with RDB+AOF persistence is acceptable for this scale with an SLA of "notifications resume within seconds of Redis restart."

---

## Alternatives Considered

### Apache Kafka

Kafka was evaluated as the primary alternative.

**Why it was rejected:**

1. **Operational complexity**: Kafka requires managing brokers, partition leadership, replication factors, and (in self-managed deployments) ZooKeeper or KRaft controllers. For a 6-person team with no Kafka experience and no dedicated infrastructure engineer, the 2-week setup timeline is unrealistic. A misconfigured Kafka cluster can silently lose data or produce phantom duplicates — failure modes the team cannot diagnose under production pressure.
2. **No existing infrastructure**: Kafka would require new AWS resources (at minimum 3 brokers for HA), new operational knowledge, and new monitoring/alerting pipelines. This exceeds the budget and timeline constraints.
3. **Over-engineered for the problem**: At 5,000 events/s peak with a notification workload (predominantly small, ephemeral messages), Kafka's partition-based model and disk-backed storage are more powerful than needed. The team would pay operational complexity costs for capabilities (thousands of topics, multi-datacenter replication, long-term log retention) that are not on the roadmap.
4. **Exactly-once semantics complexity**: Kafka's exactly-once semantics (`transactional.id`, `enable.idempotence`) are correct but require careful configuration and add latency to produce paths. The team would need significant ramp-up time to implement this correctly.

**Kafka would be the correct choice if:**
The team grows to 15+ engineers, dedicated platform/infrastructure roles exist, the message throughput exceeds 50,000 events/s sustained, or multi-datacenter replication becomes a requirement. A migration path from Redis Streams to Kafka is viable and should be revisited if scale or architectural needs demand it.

---

## Summary

| Criterion | Redis Streams | Apache Kafka |
|---|---|---|
| Team experience | High (already using Redis) | Low (no Kafka experience) |
| Setup time | < 2 weeks | > 4 weeks (learning + infra) |
| Operational overhead | Low (single Redis instance) | High (brokers, partitions, monitoring) |
| Throughput (sustained) | ~100,000 events/s | ~1,000,000+ events/s |
| Ordering guarantee | Per consumer group | Per partition |
| Exactly-once | Application-level (dedup) | Native (transactions) |
| Message retention | Configurable, memory-bound | Disk-backed, unlimited |
| WebSocket scaling | Direct via pub/sub | Requires adapter service |
| Incremental cost | $0 | 3× EC2 minimum for HA |
| Dead-letter handling | Built manually (retry stream) | Built-in routing |
| Failure mode under misconfiguration | Data loss (if Redis OOM) | Phantom duplicates, data loss |
