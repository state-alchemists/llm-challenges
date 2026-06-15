# ADR-001: Notification Subsystem Message Broker Selection

## Status

**Proposed**

## Context

Our SaaS project management platform handles ~2M tasks/month with peak load of ~500 req/s. The notification module currently executes synchronously inside the HTTP request cycle, causing:

1. **Request timeouts**: Average latency 800ms, spikes to 8s during peak hours
2. **Silent failures**: Downstream email providers or webhook endpoints cause notification loss with no retry mechanism
3. **Cascading failures**: Two incidents where slow webhook endpoints exhausted connection pools, affecting unrelated features
4. **No delivery guarantees**: Billing-critical notifications (trial expired, payment failed) lack exactly-once semantics

**Scaling requirements:**
- Decouple notifications from HTTP request cycle
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- Support WebSocket push notifications within 2 quarters
- Handle 10x traffic growth (5,000 req/s peak) without re-architecting

**Team constraints:**
- 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience on the team today
- Redis already running in production (session storage, rate limiting)
- Maximum 2-week setup/migration window before delivering value
- Modest budget; Confluent Cloud at full scale is unaffordable
- Must maintain exactly-once semantics for billing notifications

---

## Decision

**Choose Redis Streams** as the message broker for the notification subsystem.

Rationale: Redis Streams provides sufficient throughput for current and projected traffic, deploys on infrastructure the team already operates, requires no new operational dependencies, and can deliver value within the 2-week constraint. The team's existing Redis expertise eliminates the Kafka learning curve that would threaten the timeline.

---

## Consequences

### Benefits of Redis Streams

| Property | Detail |
|----------|--------|
| **Throughput** | 100,000–1,000,000 msg/s on commodity hardware — sufficient for 10x growth target (5,000 req/s × multiple notifications per event) |
| **Operational simplicity** | Runs on existing Redis infrastructure; no new services, no JVM, no Zookeeper/KRaft complexity |
| **Consumer groups** | Native `XREADGROUP`/`XACK` provide at-least-once delivery with manual acknowledgment |
| **Ordering guarantees** | Entries assigned monotonic IDs (`timestamp-millis`-sequence) ensuring per-stream ordering |
| **Message retention** | Configurable via `MAXLEN` or `MINID` policies; supports replay for debugging |
| **Delivery retry** | Application-level retry with exponential backoff using stream entry IDs as cursor |
| **Team familiarity** | Redis already in production; monitoring, backups, and operational runbooks exist |
| **Setup time** | 1–2 days to implement producer/consumer; 1–2 weeks for full migration with retry/DLQ logic |
| **Cost** | Zero additional infrastructure cost; self-hosted on existing Redis nodes |

### Drawbacks of Redis Streams

| Drawback | Mitigation |
|----------|------------|
| **Exactly-once requires application logic** | Redis Streams guarantees at-least-once (XACK); achieve exactly-once via idempotency keys stored in PostgreSQL or Redis with TTL |
| **No native dead-letter queue** | Implement DLQ as a separate stream with TTL; monitor via `XRANGE` and alerting |
| **Smaller ecosystem** | No native schema registry, but JSON payload validation in application code suffices |
| **Persistence vs. memory** | Stream entries consume memory; configure `MAXLEN` cap (~10,000 entries per stream is ~10MB) or use `MINID` eviction |
| **Horizontal scaling ceiling** | Single Redis instance is the bottleneck; however, Redis Cluster does not support streams natively. For 10x growth this is a future concern — Redis 7.x cluster mode support is maturing |

### Risks

- **Exactly-once for billing events**: Requires explicit deduplication logic (idempotency key per notification, stored with 24h TTL in Redis). This is achievable but adds implementation complexity.
- **Message loss on Redis crash**: If `appendfsync` is not `always`, a crash before fsync could lose unflushed entries. Mitigate: configure `appendfsync everysec` (default) + application-level acknowledgment after processing.
- **10x growth beyond 5 years**: If traffic exceeds ~500,000 notifications/second, Redis Streams single-instance ceiling would require re-architecting. This is outside the 10x / 2-quarter planning horizon.

---

## Alternatives Considered

### Apache Kafka

| Property | Kafka | Redis Streams |
|----------|-------|---------------|
| **Throughput** | Millions of msg/s | 100k–1M msg/s |
| **Operational complexity** | High: requires Kafka brokers, ZooKeeper or KRaft, partition management, replication factor tuning | Low: runs on existing Redis |
| **Learning curve** | Steep: no team experience; topic/partition/segment concepts unfamiliar | Minimal: Redis commands, streams are an extension |
| **Setup time** | 1–2 weeks for infrastructure; 2–4 weeks for team to reach basic proficiency | 1–2 days POC; 1–2 weeks full migration |
| **Exactly-once semantics** | Kafka Transactions provide exactly-once producer-side; consumer-side still requires idempotency | At-least-once only; requires application-level deduplication |
| **Ecosystem** | Schema registry, Kafka Connect, Streams API, rich monitoring | Native Redis tooling; fewer integrated options |
| **Cost** | Self-hosted: 3+ brokers needed for HA; managed Confluent Cloud: prohibitive at scale | Zero marginal infrastructure cost |

**Why Kafka was rejected:**

1. **Timeline incompatibility**: The 2-week constraint is firm. Provisioning Kafka brokers, configuring replication, and getting the team productive in 14 days is high-risk.

2. **No operational expertise**: The team has zero Kafka experience. Without a dedicated infrastructure engineer, debugging broker issues, partition rebalancing, or consumer lag would consume senior engineering time.

3. **Complexity without benefit**: We do not need Kafka's headline throughput (millions/sec) or its advanced stream processing capabilities. Our 10x target is ~5,000 req/s — well within Redis Streams' comfortable range.

4. **Higher operational burden**: Kafka requires monitoring consumer lag, managing partition counts, configuring retention policies, and handling broker failures. Redis Streams shares the operational burden of the existing Redis deployment the team already knows.

5. **Exactly-once is over-specified**: The requirement states "exactly-once where feasible." Kafka's exactly-once guarantee is narrower than commonly assumed (only for producer→broker, not consumer processing). Application-level idempotency is required in both Kafka and Redis Streams for end-to-end exactly-once semantics.

**Kafka is the correct choice if**: The team grows to include an infrastructure specialist, the scale exceeds 100,000 notifications/second, or a sophisticated event-sourcing architecture becomes necessary. It is not the right choice given the current constraints.

---

## Recommendation

Adopt **Redis Streams** for the notification subsystem. Implement the following:

1. **Producer**: Flask endpoint enqueues notification events to a `notifications` stream; returns 202 Accepted immediately.
2. **Consumer**: Python worker(s) use `XREADGROUP` to claim messages, process notifications (email, webhook), and `XACK` on success.
3. **Retry logic**: Failed messages are re-queued to the same stream with a delayed retry timestamp using a separate `notifications:retry` stream; implement exponential backoff with jitter.
4. **Dead-letter queue**: A `notifications:dlq` stream captures messages that exceed max retry attempts.
5. **Exactly-once for billing**: Store an idempotency key (`notification:{event_id}`) in Redis with 24h TTL before processing. Skip processing if the key exists.
6. **Monitoring**: Expose consumer lag metrics via `XLEN` and `XPENDING`.

This architecture delivers async notification processing within the 2-week window, uses existing infrastructure, and provides the delivery guarantees the product requires.