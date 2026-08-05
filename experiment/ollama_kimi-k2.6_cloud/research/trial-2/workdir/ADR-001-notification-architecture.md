# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our notification module currently runs synchronously inside the HTTP request cycle of our Python/Flask monolith. At 85,000 monthly active users and peak loads of ~500 req/s, this has produced request timeouts (average 800 ms, spikes to 8 s), silent drops on provider failures, cascading connection-pool exhaustion, and zero delivery guarantees for billing-critical events.

We must move to an asynchronous pipeline that supports:
- Retry with exponential backoff
- At-least-once delivery for all notifications
- Exactly-once semantics for billing events (e.g., "trial expired", "payment failed")
- A path to real-time WebSocket push within two quarters
- Headroom for 10× traffic growth without re-architecting

Constraints shaping this decision:
- Engineering team: 6 people (3 senior, 3 mid-level), **no dedicated infrastructure engineer**
- **No Kafka experience** on the team
- Redis is already in production (session storage, rate limiting)
- **Maximum two weeks** of setup/migration work before delivering value
- Modest budget; managed Confluent Cloud is not viable at scale

## Decision

We will build the notification subsystem on **Redis Streams**.

### Justification

The decisive factor is not raw technical supremacy but **operational fit within our constraints**. A self-hosted Kafka cluster is the stronger streaming platform on paper, yet our team size, experience gap, two-week timebox, and lack of infrastructure support make it a high-risk bet. Redis Streams provides sufficient capability for our scale at a fraction of the operational cost, and we already operate the underlying infrastructure.

**Throughput**
Redis Streams processes 100,000+ entries per second per node. Even assuming a generous fan-out of 10 notifications per request, our 500 req/s peak translates to ~5,000 messages/sec—two orders of magnitude below Redis capacity. The 10× growth target (50,000 messages/sec) still sits comfortably within a single Redis instance, let alone a small primary-replica deployment.

**Ordering guarantees**
Redis Streams assigns monotonically increasing entry IDs (`XADD`) and consumers read in insertion order (`XREADGROUP`). This gives us strict FIFO ordering *per stream*, which is sufficient because our ordering requirement is per-user or per-task notification sequencing, not global cross-topic ordering.

**Message retention**
Redis Streams uses memory-bound retention (`MAXLEN`, `XTRIM`, or TTL-based eviction). For a notification pipeline, this is acceptable: notifications are short-lived buffers (hours to a few days), not immutable event logs. We do not need multi-year replay capability; we need retries across minutes or hours. Retention will be configured per stream (e.g., 100,000 entries or 48 hours), which covers our retry windows with margin.

**Consumer groups**
Redis provides native consumer groups (`XGROUP CREATE`, `XREADGROUP`, `XPENDING`, `XCLAIM`) with semantics analogous to Kafka: multiple consumers balance partitions (streams), process messages, and explicitly acknowledge (`XACK`). Pending messages can be claimed by other consumers after a timeout, enabling graceful failover and retry.

**Exactly-once semantics for billing events**
Redis Streams does not offer broker-level exactly-once delivery. We will implement **application-level idempotency**:
- Billing notifications carry a deterministic idempotency key (e.g., `billing:{user_id}:{event_type}:{timestamp_day}`).
- Before processing, the consumer attempts to insert the key into a Redis SET with a TTL via `SET NX`.
- If the key exists, the message is acknowledged and dropped as a duplicate.
- This pattern is simple to reason about in Python, requires no complex transaction coordinators, and is trivial to monitor.
While this shifts responsibility to the application, it is a robust and well-understood pattern that our senior engineers can implement and review in days, not weeks.

**Operational complexity**
Redis is already deployed, monitored (metrics, alerting, backups), and understood by the entire team. Adding Streams is a configuration change (`MAXLEN`, consumer-group setup), not a new technology introduction. By contrast, self-hosted Kafka requires broker tuning, partition planning, consumer-lag monitoring, replication-factor decisions, and on-call expertise our team does not possess. Attempting to stand up production-grade Kafka in two weeks with zero prior experience would yield an under-tuned cluster that becomes a liability.

## Consequences

### Pros
- **Minimal operational overhead**: Leverages existing Redis infrastructure, monitoring, and team expertise.
- **Fast time-to-value**: Can be prototyped in days and in production within the two-week limit.
- **Sufficient throughput**: Handles current and 10× projected load with headroom.
- **Natural WebSocket path**: Redis pub/sub (already available) plus Streams gives us a unified data plane for async notifications and future real-time push.
- **Lower total cost**: No additional licensing, no extra AWS instances for brokers/ZooKeeper, no new managed service.

### Cons
- **Memory-bound retention**: If a consumer is down for an extended period beyond our configured `MAXLEN`/TTL, messages are evicted and lost. We must size buffers for our maximum expected outage window (e.g., 24–48 hours) and alert on consumer lag.
- **No native exactly-once**: The idempotency layer is our responsibility; a bug in the application code could duplicate a billing notification.
- **Less mature ecosystem**: No equivalent to Kafka Connect or mature stream-processing frameworks (e.g., Kafka Streams, ksqlDB). Any stream processing logic (filtering, enrichment) will be custom Python code.
- **Potential future migration**: If we eventually outgrow Redis Streams or need deep log compaction and replay, we may need to migrate to Kafka. This risk is acceptable because the decision is reversible: Redis Streams uses standard stream semantics, and a future migration path to Kafka is well-documented.

## Alternatives Considered

### Apache Kafka (rejected)

Kafka is technically superior in three dimensions relevant to this problem:
1. **Disk-based retention and replay**: Kafka retains messages on disk for arbitrary durations, enabling back-fill and audit replay.
2. **Exactly-once semantics**: Idempotent producers and transactions provide broker-level exactly-once delivery.
3. **Ecosystem maturity**: Kafka Connect, stream-processing libraries, and extensive community operational tooling.

We rejected it because the operational barrier is prohibitive for our team and timeline:
- **Experience gap**: No engineer has deployed, tuned, or debugged Kafka in production. Learning this while under a two-week deadline is unsafe.
- **Infrastructure burden**: A minimal production Kafka deployment requires broker nodes (ideally 3 for fault tolerance), ZooKeeper or KRaft coordination, partition planning, and replication tuning. Without a dedicated infrastructure engineer, this becomes a persistent drag on the team.
- **Budget constraint**: Managed Confluent Cloud is explicitly ruled out; self-hosted is the only option, amplifying the operational burden above.
- **Overcapacity for current needs**: Kafka’s strengths matter most at multi-thousand-message-per-second scale with complex stream topologies. Our notification domain is a straightforward produce-consume-ack pipeline; Kafka’s power is unnecessary weight today.

Given that our primary risk is **delivery reliability and team velocity**, not throughput ceiling, Redis Streams is the proportionate choice. We will revisit Kafka if we cross a scale or complexity threshold where its operational overhead is justified by feature requirements we cannot satisfy with Redis.
