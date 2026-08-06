# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

---

## Context

### The Problem

Our notification module sends emails and webhooks synchronously inside the HTTP request cycle. This has caused:

- **Request timeouts**: Average latency 800ms, spiking to 8s at peak hours
- **Silent failures**: No retry, no dead-letter queue; failed notifications are dropped
- **Cascading failures**: A slow webhook endpoint twice exhausted the connection pool, taking down unrelated features
- **No delivery guarantees**: Billing-critical notifications (trial expired, payment failed) lack exactly-once semantics

### Scaling Targets

- Decouple notifications from the HTTP request cycle (async processing)
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- WebSocket push notifications within 2 quarters
- Handle 10x traffic growth without re-architecting

### Current System

| Component | Detail |
|---|---|
| Backend | Python/Flask monolith (~50k lines) |
| Database | PostgreSQL (single primary, one read replica) |
| Infrastructure | 4 web servers on AWS behind nginx |
| Cache | Redis (session storage + rate limiting) |
| Peak load | ~500 req/s |
| Monthly volume | ~2M tasks created; 85,000 MAU |

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer
- **Kafka experience**: None on the team today
- **Redis experience**: Already in production for session storage and rate limiting
- **Timeline**: Must deliver value within 2 weeks; no multi-week infrastructure projects
- **Budget**: Modest; cannot afford managed Confluent Cloud at scale
- **Critical requirement**: Exactly-once semantics for billing notifications

---

## Decision

**Chosen option: Redis Streams**

Redis Streams is the correct choice for this subsystem given our constraints. It delivers the required async processing, retry semantics, and delivery guarantees using infrastructure the team already operates — eliminating the multi-week onboarding and operational overhead that Kafka would impose.

---

## Consequences

### Pros

1. **Operational continuity**: Redis is already running in production. No new servers, no new operational relationships, no new monitoring to wire up. The team manages what they already know.
2. **Fast time-to-value**: Redis Streams syntax (`XADD`, `XREAD`, `XACK`, `XGROUP`) is learnable in a day. A Python consumer worker using `redis-py` with stream support can be running in a sprint. Entire subsystem deliverable in well under 2 weeks.
3. **Sufficient throughput**: At 500 req/s peak, Redis Streams handles this comfortably — `XADD` and `XREADGROUP` sustain tens of thousands of operations per second on modest hardware. This leaves headroom for 10x growth.
4. **Consumer groups with PEL**: The consumer group model (`XGROUP CREATE`, `XREADGROUP`) tracks unacknowledged messages in the Pending Entries List (PEL). On worker crash, unacknowledged messages are automatically redelivered — providing at-least-once delivery out of the box.
5. **Exactly-once for billing**: Achieved via a deduplication layer: producers write notifications with a deterministic idempotency key (e.g., `hash(user_id + event_type + event_id)`), consumers check a Redis SET or a DB table before processing. This pattern is straightforward and well-tested.
6. **Retry with exponential backoff**: Consumer workers manage their own retry state — track retry count in a hash, delay on re-read based on exponential backoff. Dead-letter after N retries (e.g., write to a separate `notifications.dlq` stream).
7. **No licence cost**: Self-managed Redis is included in the existing deployment. No additional infrastructure cost.
8. **Scales to WebSocket push**: A separate consumer group on the same stream can serve WebSocket fan-out workers within 2 quarters, sharing the event stream with email/webhook workers.

### Cons

1. **Message retention is limited**: Redis Streams retain messages only as long as consumers are active and the `MAXLEN` / `MINID` trimming policy is applied. Long-running consumers or停顿 can cause message loss if not configured carefully. Mitigation: set `MAXLEN` appropriately and ensure consumer acknowledgment before trim.
2. **No native cross-datacenter replication in open-source Redis**: If high availability across AZs is required, Redis Cluster or Redis Sentinel adds operational complexity. For a 6-person team with no dedicated infra engineer, this is the most credible failure mode. Mitigation: single Redis instance with RDB+AOF backup is sufficient for the notification use case at this scale, with a clear migration path to Redis Cluster if needed.
3. **Less ecosystem tooling**: Kafka has decades of third-party tooling (Kafka Connect, Schema Registry, MirrorMaker). Redis Streams has a smaller ecosystem — monitoring is primarily through Redis `INFO` and consumer lag metrics via `XPENDING`.
4. **Not a log, it's a stream**: Redis Streams behave like a log-structured stream, but unlike Kafka partitions, they have different semantics around consumer group state. The mental model is slightly different; the team will need to internalize the PEL (Pending Entries List) as the source of truth for in-flight messages.
5. **Exactly-once requires application-layer work**: Kafka's exactly-once semantics (transactions + idempotent producer) are more built-in. With Redis Streams, exactly-once for billing notifications requires the producer-side deduplication pattern described above — a small but real implementation concern.

---

## Alternatives Considered

### Apache Kafka

Kafka would be the standard choice in a larger organization with dedicated infrastructure engineers and an existing Kafka deployment. Its characteristics are:

| Property | Kafka | Redis Streams |
|---|---|---|
| Throughput | 1M+ msg/s (cluster) | 50k–100k msg/s (single instance) |
| Message retention | Days to years, log-segmented | Bounded by `MAXLEN` (default ~512GB) |
| Consumer groups | Mature, per-partition ordering | Mature, per-stream consumer groups |
| Exactly-once | Native via transactions + idempotent producer | Application-layer deduplication |
| Operational complexity | High (cluster, partitions, replication, leader election) | Low (same Redis already operated) |
| Learning curve | Steep — no team experience | Low — team uses Redis today |
| Setup time | 2–6 weeks for production-ready cluster | 3–7 days |
| Cost | 3+ broker instances minimum for HA | Zero incremental infra |

**Why Kafka is rejected:**

1. **No Kafka experience**: The team has zero production experience with Kafka. Getting a production-ready cluster (replication factor 3, proper partition assignment, consumer group lag monitoring, topic retention policies) takes weeks of learning alongside the actual notification work.
2. **Operational overhead**: A 6-person team with no dedicated infra engineer cannot afford the ongoing operational burden of a Kafka cluster — broker failures, partition rebalancing, JVM tuning, schema registry management.
3. **Budget mismatch**: Confluent Cloud is the managed option that eliminates operational overhead, but it is cost-prohibitive at the "modest budget" stated. Self-managed Kafka on EC2 requires a minimum of 3 brokers for HA, plus ZooKeeper or KRaft — significant infra cost and complexity.
4. **2-week deadline**: A production Kafka deployment — even a simple 3-broker cluster — cannot be safely configured, tested, and migrated to within 2 weeks by engineers learning it for the first time.
5. **Throughput is overkill**: The system peaks at 500 req/s. Kafka is architected for million-message-per-second throughput. This is a significant mismatch — the complexity budget Kafka demands is not justified by the actual load.

Kafka is the right choice when you have dedicated platform engineers, an existing Kafka deployment, throughput in the hundreds of thousands of messages per second or more, or a multi-quarter timeline to get it right. None of those conditions apply here.

---

## Summary

Redis Streams satisfies every stated requirement — async processing, retry with exponential backoff, at-least-once delivery, and implementable exactly-once for billing — while staying within the team's existing operational knowledge, the 2-week timeline, and the modest budget. Kafka would add weeks of learning and significant operational complexity for throughput the system will never need at this stage.

**Recommendation**: Build the notification subsystem on Redis Streams. Implement producer-side deduplication keys for billing events, use consumer groups with `XACK`-based retry, and set `MAXLEN` on streams to bound memory. Migrate to Kafka only when throughput exceeds ~50,000 notifications/second or the team grows a dedicated platform function.
