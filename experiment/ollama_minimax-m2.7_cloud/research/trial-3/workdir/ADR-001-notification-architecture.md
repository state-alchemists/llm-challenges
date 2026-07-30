# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

Our SaaS project management platform handles ~2M tasks/month with peak load of ~500 req/s. The current synchronous notification system (emails and webhooks) causes request timeouts (avg 800ms, spikes to 8s), silent failures with no retry, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical events.

**Requirements:**
- Decouple notifications from HTTP request cycle
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- Support WebSocket push notifications within 2 quarters
- Handle 10x traffic growth without re-architecting

**Constraints:**
- Team of 6 (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience; Redis already in production
- 2-week maximum setup/migration time
- Modest budget (cannot afford managed Confluent Cloud)
- Must maintain exactly-once semantics for billing notifications

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

## Justification

### Operational Fit (Primary Factor)

The team has **no Kafka experience** and **no dedicated infrastructure engineer**. Kafka's operational burden—partition management, replication factor configuration, leader election, bootstrap server management, and (in older versions) Zookeeper coordination—is significant even for experienced teams. Redis Streams leverages existing infrastructure and Redis expertise already on the team.

### Time-to-Value

Redis Streams can be operational within days, not weeks. The team will write producers in Python/Flask, consume with a lightweight worker process, and use Redis for deduplication via stream entry IDs. Kafka requires cluster provisioning, topic configuration, consumer group setup, and operational runbooks before delivering value.

### Throughput Adequacy

At 500 req/s peak (2M tasks/month), we require ~50-100 msg/s of notification traffic (emails + webhooks per task event). Redis Streams handles **100k–1M messages/second** on commodity hardware—three orders of magnitude above our requirement. Kafka's million-message/s throughput is irrelevant at our scale; we are not near Redis Streams' ceiling.

### Existing Infrastructure

Redis is already running for session storage and rate limiting. Adding Streams is incremental infrastructure, not a new system. No additional servers, no new dependencies, no coordination overhead.

### Delivery Guarantees

Redis Streams' `XREADGROUP` + `XACK` pattern provides **at-least-once** delivery with message acknowledgment. For billing notifications requiring exactly-once, we implement application-level deduplication using a Redis SET with task+notification type as the key, checked before sending. This is straightforward given Redis is already in the stack.

## Consequences

### Pros

1. **Low operational overhead**: Redis is already monitored, backed up, and familiar to the team.
2. **Fast implementation**: Streams API is available in redis-py; producers and consumers can be written in an afternoon.
3. **Familiar tooling**: redis-cli, Redis Desktop Manager, and existing Redis monitoring all work without new dashboards.
4. **Consumer groups with ACK**: `XREADGROUP` ensures each message is processed by one consumer; `XACK` tracks completion; `XPENDING` reveals stuck workers.
5. **Message retention**: Configurable via `MAXLEN` or `MINID` policies; adequate for replay during outages.
6. **Scalable to 10x**: At 5,000 req/s, Redis Streams remains well within its performance envelope; horizontal Redis clustering can scale further if needed.
7. **Dead-letter handling**: Failed messages after N retries go to a dedicated `notifications.dlq` stream for manual inspection.
8. **WebSocket readiness**: A single Redis Pub/Sub channel or Streams consumer can fan out to WebSocket connections without architecture changes.

### Cons

1. **Memory-bound retention**: Unlike Kafka's log-based retention, Redis Streams stores messages in memory. At high volume with long retention windows, memory usage grows. Mitigation: cap retention with `MAXLEN ~` and process promptly.
2. **No native exactly-once**: Requires application-level deduplication for billing events. Kafka's transactional producers offer exactly-once out of the box, but at significant operational complexity.
3. **Limited message history**: While Streams supports reading from arbitrary offsets, the in-memory nature means very old messages (beyond retention) are unavailable for replay. For auditability, we must write billing events to PostgreSQL as the system of record.
4. **No native compaction**: Kafka's message compaction is useful for late-joining consumers. Redis lacks this; consumers must handle gaps.
5. **Single-node threading**: Redis Streams performance depends on Redis instance resources. Active-active Redis Cluster adds complexity but is not needed at our current scale.

## Alternatives Considered

### Apache Kafka

**Rejected.**

Kafka offers superior throughput (millions of msg/s), durable log-based retention, native exactly-once semantics via transactional producers, and battle-tested consumer group offset management. However, for our context:

- **Operational complexity is prohibitive**: Kafka requires cluster sizing, partition assignment, replication factor tuning, and ISR (In-Sync Replicas) management. A 6-person team with no Kafka experience cannot reliably operate a Kafka cluster alongside their primary product work.
- **Setup time exceeds constraint**: Self-managed Kafka (without Confluent Cloud) requires at minimum: broker provisioning, ZooKeeper or KRaft configuration, topic creation with appropriate partition counts and replication factors, consumer group setup, and operational runbooks. This easily exceeds our 2-week constraint.
- **Overengineering at our scale**: Kafka's strengths (millions of msg/s, multi-day retention, cross-datacenter replication) are irrelevant at 500 req/s. We would pay the full operational cost for capabilities we do not need.
- **Budget reality**: Managed Confluent Cloud would solve operations but costs $0.10+/GB, and at 2M tasks/month with notification payloads, costs would be material. Self-managed Kafka on EC2 requires dedicated infrastructure we have not budgeted.

Kafka would be the correct choice if we had an infrastructure team, planned to process millions of events per second, or needed cross-datacenter replication. None of these apply today.

## Summary

Redis Streams meets all functional requirements—async processing, retry with backoff, at-least-once delivery, and deduplication for billing—while honoring the team's operational constraints. Kafka's operational overhead and setup time make it unsuitable for a 6-person team with a 2-week deadline and no existing Kafka expertise. We proceed with Redis Streams; if throughput or retention requirements change materially, we revisit Kafka in a future ADR.
