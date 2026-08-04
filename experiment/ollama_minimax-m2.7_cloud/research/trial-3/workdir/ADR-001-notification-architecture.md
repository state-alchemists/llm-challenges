# ADR-001: Notification Subsystem Message Broker Selection

## Status

**Proposed**

## Context

The current notification module runs synchronously inside the HTTP request cycle, causing request timeouts (avg 800ms, spikes to 8s), silent failures with no retry, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical events.

**Requirements:**
- Decouple notifications from HTTP request cycle (async processing)
- Retry with exponential backoff
- At-least-once delivery; exactly-once for billing-critical events
- Support WebSocket push notifications within 2 quarters
- Handle 10x traffic growth without re-architecting

**System Profile:**
- 85,000 MAU, ~2M tasks/month, peak ~500 req/s
- 6-engineer team (3 senior, 3 mid), no dedicated infrastructure engineer
- Existing: Python/Flask monolith, PostgreSQL, Redis (session/rate limiting)
- No Kafka experience on team
- 2-week maximum migration window
- Modest budget (cannot afford Confluent Cloud at scale)

## Decision

**Choose Redis Streams.**

Redis Streams is the correct choice given our team constraints, timeline, and existing infrastructure. It provides sufficient throughput for our current and projected load, offers consumer group semantics with at-least-once delivery, reuses our existing Redis investment, and can be operational within days rather than weeks.

## Consequences

### Pros of Redis Streams

| Property | Detail |
|----------|--------|
| **Operational simplicity** | Team already runs Redis for session storage and rate limiting. No new service to deploy, monitor, or maintain. Minimal operational overhead. |
| **Throughput** | 100,000–500,000 events/sec per Redis instance (far exceeds our peak of 500 req/s with room for 10x growth). |
| **Ordering guarantees** | Messages within a consumer group are delivered in insertion order via XREADGROUP. |
| **Consumer groups** | XREADGROUP + XACK provides per-group offset tracking, enabling multiple consumers in a group with automatic load balancing and restart recovery. |
| **At-least-once delivery** | XREADGROUP with XACK ensures messages are only marked processed after successful handling. Unacknowledged messages are redelivered. |
| **Exactly-once for billing** | Achievable via idempotent message handlers. Generate a unique notification ID per event, store processed IDs in a dedup set (Redis SET or PostgreSQL table), and skip reprocessed messages on redelivery. |
| **Message retention** | Configurable via MAXLEN (exact) or MAXLEN~ (approximate) trimming, or by ID-based retention period. |
| **Consumer lag visibility** | XPENDING command exposes pending message count and idle times per consumer group. |
| **Learning curve** | Team has existing Redis familiarity. Redis Streams commands (XADD, XREADGROUP, XACK, XPENDING) are learnable in hours. |
| **Setup time** | Days, not weeks. A working prototype can be running by end of day one. Full migration within the 2-week window. |
| **Cost** | Zero additional infrastructure cost. Reuse existing Redis instance (or add a small Redis Sentinel/Cluster for HA if needed). |
| **WebSocket readiness** | Redis Pub/Sub can supplement Streams for fan-out to WebSocket servers. A single Redis instance supports both notification streaming and real-time push. |

### Cons of Redis Streams

| Property | Detail |
|----------|--------|
| **No native partitioning** | Unlike Kafka partitions, Redis Streams does not auto-shard across nodes. Single-instance throughput is bounded by one node's CPU. Scale-out requires Redis Cluster (added complexity). |
| **Exactly-once requires app-level work** | Kafka offers transaction-based exactly-once out of the box. Redis Streams requires idempotent handlers with dedup logic built into consumers. |
| **No native dead-letter queue** | Must implement DLQ manually (route failed messages after N retries to a separate stream via XADD). |
| **Persistence tradeoff** | If Redis is restarted with `appendonly yes`, messages survive; without persistence, messages in flight can be lost on hard crash (mitigated by AOF + proper consumer group offset management). |
| **Message size limits** | Redis has a 512MB value size limit per key; notification payloads well under this, but a payload explosion could hit it. |
| **Maturity for event sourcing** | Kafka is purpose-built for event streaming with log compaction, schema registry, and connector ecosystem. Redis Streams is newer (2017) with a smaller ecosystem. |
| **Replication lag** | If using Redis replication, there is a small window where a primary failure could lose unacknowledged messages. Use Redis Sentinel or Cluster for HA. |

## Alternatives Considered

### Apache Kafka

| Property | Redis Streams | Apache Kafka |
|----------|---------------|--------------|
| **Throughput** | 100K–500K/sec (single node) | Millions/sec (clustered) |
| **Ordering** | Per consumer group | Per partition |
| **Exactly-once** | App-level idempotency | Native transactions (exactly-once semantics) |
| **Consumer groups** | Yes | Yes (mature) |
| **Message retention** | Configurable trimming | Log retention (days/weeks/indefinite) |
| **Operational complexity** | Low | High |
| **Learning curve** | Low (Redis familiarity) | Steep (no experience) |
| **Setup time** | Days | Weeks (cluster setup, topic config, monitoring, alerting) |
| **Infrastructure cost** | Reuse existing Redis | New EC2 instances (3+ for HA), or Confluent Cloud |
| **Ecosystem** | Smaller | Large (Kafka Connect, Schema Registry, ksqlDB, etc.) |

**Why Redis Streams wins over Kafka for this team:**

1. **Timeline constraint (2 weeks):** Kafka requires cluster sizing, broker configuration, Zookeeper/KRaft setup, topic partitioning strategy, consumer group configuration, monitoring dashboards, and operational runbooks. Our team has no Kafka experience; 2 weeks is insufficient to ship production-ready Kafka.

2. **Team composition:** Six engineers, none dedicated to infrastructure. Kafka's operational burden (rebalancing, leader election, partition reassignment, disk management) requires specialized knowledge we do not have.

3. **Scale match:** Our peak is 500 req/s. Redis Streams handles this with a single small Redis instance. Kafka's architecture is designed for orders-of-magnitude higher throughput; we would pay for complexity we do not need.

4. **Existing Redis investment:** We already run Redis. Adding Streams is incremental. Kafka introduces an entirely new system to operate.

5. **Exactly-once for billing:** Kafka's exactly-once is more robust, but Redis Streams + idempotent handlers achieves the same guarantee with acceptable complexity for our billing notification volume.

**When Kafka would be correct:**
- If the team had Kafka experience or a dedicated platform/infrastructure engineer
- If the system required millions of events per second
- If the notification system would evolve into a full event-sourcing architecture with multiple downstream consumers
- If the timeline allowed 6+ weeks for proper Kafka deployment and team ramp-up
- If budget allowed managed Confluent Cloud with enterprise support

## Recommendation

**Implement Redis Streams for the notification subsystem.** This delivers immediate value within the 2-week constraint, leverages existing infrastructure, matches our throughput requirements with headroom for 10x growth, and provides the delivery guarantees (at-least-once, with exactly-once for billing via idempotency) that the system critically needs.

Kafka is the correct technology for high-throughput, multi-consumer, event-sourcing workloads at scale—but it is overkill for our current team and timeline, and the operational complexity would delay delivering value by months.

### Implementation Notes

1. **Dedup for billing notifications:** Assign a UUIDv5 or hash-based notification ID per event. On consumer, check `SISMEMBER processed:notification_ids <id>` before processing. After successful send, `SADD processed:notification_ids <id>` with a TTL (e.g., 7 days).

2. **Retry with exponential backoff:** Track retry count in message metadata (`XADD notifications * retry_count 0 ...`). Consumer checks retry count; if below threshold, `XADD notifications.retry <same_payload>` with delayed execution (via sorted set + scheduler). After max retries, `XADD notifications.dlq *`.

3. **WebSocket push:** Use Redis Pub/Sub channels (`PUBLISH user:{id} payload`) alongside Streams. WebSocket servers subscribe to user-specific channels and push to connected clients.

4. **Redis HA:** Enable AOF persistence with `appendfsync everysec` minimum. Consider Redis Sentinel for automatic failover if HA is required before going to production.
