# ADR-001: Notification Subsystem Message Broker

**Status:** Proposed

**Date:** 2026-06-23

---

## Context

### Problem Statement

The notification module sends emails and webhooks synchronously inside the HTTP request cycle. This causes:

- **Request timeouts**: Average latency 800ms, spiking to 8s at peak hours, because notification delivery blocks the HTTP response.
- **Silent failures**: If an email provider or webhook endpoint is down, the notification is dropped with no retry and no dead-letter queue.
- **Cascading failures**: Two production incidents this year where a slow webhook endpoint exhausted connection pools, taking down unrelated features.
- **No delivery guarantees**: Billing-critical notifications (trial expired, payment failed) require exactly-once delivery, which the current system cannot provide.

### System Profile

| Metric | Value |
|--------|-------|
| Monthly active users | 85,000 |
| Tasks created per month | ~2M |
| Peak request rate | ~500 req/s |
| Team size | 6 engineers (3 senior, 3 mid-level) |
| Dedicated infra engineer | None |
| Existing message broker | None |
| Existing Redis | Yes (session storage, rate limiting) |

### Scaling Requirements

1. Decouple notifications from the HTTP request cycle (async processing)
2. Retry with exponential backoff
3. At-least-once delivery for billing events; exactly-once where feasible
4. Real-time WebSocket push notifications within 2 quarters
5. Handle 10x traffic growth without re-architecting

### Constraints

- **Time-to-value:** No more than 2 weeks of setup and migration work before delivering initial value
- **Operational burden:** Team has no Kafka experience and no dedicated infrastructure engineer
- **Budget:** Cannot afford managed Confluent Cloud at full scale; modest budget only
- **Existing investment:** Redis is already in production and operational

---

## Decision

**Choose Redis Streams as the message broker for the notification subsystem.**

Redis Streams provides sufficient throughput for current and projected scale, requires no new infrastructure, leverages existing Redis expertise, and can be implemented within the 2-week constraint. Billing-critical exactly-once semantics are achieved through application-level deduplication, which is required regardless of which broker is chosen.

---

## Technical Comparison

### Throughput

| Broker | Nominal throughput | Notes |
|--------|-------------------|-------|
| Apache Kafka | ~1–6 GB/s (clustered, optimized) | Overkill for 500 req/s peak |
| Redis Streams | ~500K–1M events/s per node | Far exceeds 10x growth target |

At 500 req/s peak with 10x growth targeting 5,000 req/s, Redis Streams comfortably handles the load on a single node. Kafka's throughput advantage is irrelevant at this scale.

### Ordering Guarantees

| Broker | Ordering model | Notes |
|--------|---------------|-------|
| Apache Kafka | Per-partition ordering | Guarantees ordering within a topic partition; requires careful partition key design |
| Redis Streams | Per-consumer-group ordering | `XREADGROUP` delivers messages in stream order within a consumer group; single consumer gets FIFO |

Both provide sufficient ordering for notification semantics. For billing events, ordering matters within a user account — both brokers satisfy this when consumer groups are keyed by `user_id`.

### Message Retention

| Broker | Retention | Notes |
|--------|-----------|-------|
| Apache Kafka | Configurable (hours to unlimited) | Default typically 7 days; ideal for replay |
| Redis Streams | Configurable via `MAXLEN` or `MINID` | Can cap stream size; supports trimming like Kafka |

Kafka has superior replay capabilities for event sourcing patterns. For notification delivery, replay is not a primary requirement — a 7-day retention window (achievable in both) is sufficient.

### Consumer Groups

| Broker | Consumer group support | Notes |
|--------|----------------------|-------|
| Apache Kafka | Native, mature | Named consumer groups; rebalance protocol; static membership |
| Redis Streams | `XREADGROUP` + `XGROUP` | Consumer groups via `XGROUP CREATE`; equivalent semantics to Kafka consumer groups |

Both support the fan-out pattern needed for multi-channel notifications (email, webhook, WebSocket push) via separate consumer groups reading the same stream.

### Exactly-Once Semantics

| Broker | Guarantee level | Implementation |
|--------|----------------|----------------|
| Apache Kafka | Exactly-once in Kafka (idempotent producers + transactions) | Built-in but operationally complex; requires transactions across input and output topics |
| Redis Streams | At-least-once only | No native exactly-once; achieved via application-level deduplication using event IDs |

**Important caveat:** Kafka's exactly-once guarantee applies only within Kafka itself. Any external side effect (email sent, webhook called) is not protected by Kafka — it only prevents duplicate ingestion into Kafka. Application-level deduplication is required for downstream exactly-once delivery regardless of broker. Redis Streams with application-level deduplication using `event_id` is equivalent in practice.

### Operational Complexity

| Factor | Apache Kafka | Redis Streams |
|--------|-------------|---------------|
| Infrastructure | Requires Kafka brokers + ZooKeeper or KRaft quorum | Uses existing Redis (no new servers) |
| Cluster management | Complex: broker failure detection, partition rebalancing, leader election | None beyond existing Redis operations |
| Monitoring | JMX metrics, Confluent tools, offset lag monitoring | Existing Redis monitoring stack |
| Learning curve | Steep: partition assignment, ISR tuning, producer acks, retries | Low: `XADD`, `XREADGROUP`, `XCLAIM` — familiar Redis primitives |
| Onboarding time | 2–4 weeks for a team with no experience | 1–3 days |
| Operational burden | High (requires infra expertise) | Low (leverages existing Redis expertise) |

The team has no dedicated infrastructure engineer. Kafka's operational complexity would consume senior engineering time indefinitely. Redis Streams requires no new infrastructure and uses primitives the team already understands.

---

## Consequences

### Pros of Redis Streams

1. **No new infrastructure:** Redis is already running in production. No new servers, no new operational responsibility.
2. **Fast onboarding:** The team understands Redis. `XADD`, `XREADGROUP`, and `XCLAIM` can be learned in hours. Migration can complete well within the 2-week constraint.
3. **Operational simplicity:** Redis is a single-threaded, well-understood system. No broker quorum, no partition rebalancing, no ISR tuning.
4. **Sufficient throughput:** 500K–1M events/s per node exceeds the 10x growth target by two orders of magnitude.
5. **Consumer groups:** `XREADGROUP` provides equivalent fan-out capability to Kafka for multi-channel notifications (email, webhook, WebSocket).
6. **Dead-letter handling:** `XCLAIM` with `MINIDLETIME` implements the retry-with-exponential-backoff pattern required for failed deliveries.
7. **Existing monitoring:** Redis monitoring (already in place for session storage) covers the new stream without additional tooling.
8. **Cost:** Uses existing Redis instance; no additional cloud spend.

### Cons of Redis Streams

1. **No native exactly-once:** Application-level deduplication is required for billing-critical events. This is not difficult — store processed `event_id` values in a Redis set with TTL — but it is additional code that Kafka's transaction API would handle internally.
2. **Persistence vs. throughput trade-off:** If Redis is configured for `appendfsync = no` (for speed), messages in flight during a crash can be lost. Must use `appendfsync = always` or `appendfsync = everysec` with a replication factor ≥ 1 for notification durability. This is an existing Redis operational concern, not a new one.
3. **No native replay:** Unlike Kafka's offset-based replay, Redis Streams requires tracking consumer position manually if replay is needed. For notification delivery (not event sourcing), this is rarely needed.
4. **Scaling beyond one Redis node:** Redis Cluster mode does not support Streams with consumer groups across cluster slots in the same way single-node does. If the 10x growth target expands to 100x, re-evaluation would be needed — but the current trajectory does not suggest this is imminent.
5. **WebSocket push integration:** WebSocket server will need to subscribe to Redis Streams as a consumer group. This is straightforward but adds a dependency on Redis from the WebSocket layer.

### Mitigations for Cons

- **Exactly-once for billing events:** Implement deduplication using `SETNX` with the event ID as the key and a 24-hour TTL. Before processing a billing event, check-and-set. This pattern is idempotent and race-condition-free.
- **Durability:** Ensure Redis `appendfsync` is set to `everysec` (sweet spot between durability and performance). With a read replica, the replication factor provides data safety.
- **WebSocket scaling:** WebSocket servers can be scaled horizontally, each subscribing to the same consumer group. Redis Streams handles fan-out distribution automatically.

---

## Alternatives Considered

### Apache Kafka

**Rejected.**

Kafka offers superior throughput (millions of events/s in clustered mode), native exactly-once semantics via idempotent producers and transactions, superior replay capabilities, and a richer ecosystem for event sourcing. However:

1. **Infrastructure burden:** Kafka requires a cluster of brokers (minimum 3 for HA), ZooKeeper or KRaft quorum management, and partition leadership tracking. The team has no dedicated infrastructure engineer. Operating a Kafka cluster in production requires expertise the team does not have.

2. **Learning curve:** Partition key design, producer acknowledgments (`acks=all` vs. `acks=1`), ISR tuning, consumer group rebalancing policies, and exactly-once configuration are non-trivial. A 6-person team with 2 weeks to deliver value cannot absorb this.

3. **Cost and complexity:** Self-managed Kafka on AWS requires EC2 instances for brokers, separate instances for ZooKeeper/KRaft, careful network configuration, and monitoring. Managed Confluent Cloud would simplify operations but exceeds the stated budget.

4. **Throughput mismatch:** At 500 req/s peak (5,000 req/s at 10x growth), the team's scale is orders of magnitude below Kafka's sweet spot. Kafka is designed for tens of thousands of events per second. Redis Streams handles 500K–1M events/s — still 100x headroom above the growth target.

5. **Exactly-once is overstated:** Kafka's exactly-once guarantee applies only to Kafka-to-Kafka data pipelines. For email or webhook notifications (the actual delivery in this system), application-level deduplication is still required. The advantage is smaller than it appears.

**Kafka would be the right choice** if the team anticipated event-sourcing workloads, required sub-millisecond latency at very high throughput, or had dedicated platform/infrastructure engineers. None of these conditions apply.

---

## Recommendation

Implement the notification subsystem using **Redis Streams** with:

- A single `notifications` stream keyed by `user_id` for ordering within a user account
- Separate consumer groups: `email-notifications`, `webhook-notifications`, `websocket-notifications`
- `XCLAIM` with exponential backoff for dead-letter reprocessing
- Application-level deduplication via `SETNX` with event ID keys for billing-critical notifications
- `appendfsync = everysec` on Redis for durability

The migration can be completed in 1–2 weeks by one senior engineer while others continue feature development. No new infrastructure is required. The team's existing Redis expertise is sufficient for operations and debugging.
