# ADR-001: Notification Subsystem — Asynchronous Message Broker

**Status:** Proposed

---

## Context

The Notifier subsystem sends email and webhook notifications when tasks are created, updated, assigned, or completed. Currently, this happens synchronously inside the Flask HTTP request cycle, producing four classes of failures:

1. **Request timeouts** — average latency 800 ms, spikes to 8 s during peak hours.
2. **Silent failures** — downstream provider outages drop notifications with no retry or dead-letter queue.
3. **Cascading failures** — slow webhook endpoints exhaust the PostgreSQL and HTTP connection pools, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications (trial expiry, payment failure) have no mechanism for exactly-once delivery.

We need an async message broker that decouples notification dispatch from the request cycle, supports retry with exponential backoff, and enables exactly-once delivery for billing events. Within two quarters, we also need to add real-time WebSocket push without a second infrastructure build.

### Constraints

- **Team:** 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Existing infrastructure:** Redis is already in production (session storage, rate limiting). PostgreSQL single primary + one replica.
- **Experience:** No team member has operated Kafka in production.
- **Timeline:** Must deliver user-visible value within two weeks of starting.
- **Budget:** Modest — managed Kafka (Confluent Cloud, AWS MSK) at full scale is out of reach.
- **Scale:** Currently ~500 req/s peak, ~2M tasks/month. Must handle 10× growth without re-architecting.
- **Correctness:** Exactly-once delivery for billing notifications is non-negotiable.

---

## Decision

**Adopt Redis Streams** as the notification message broker, operating on the existing Redis instance.

Redis Streams provides the consumer-group model, at-least-once delivery, message acknowledgment, and pending-entry management (auto-claim) needed for reliable async processing — all on infrastructure the team already runs and knows. Exactly-once semantics for billing events will be achieved at the application layer via idempotent consumers backed by a PostgreSQL dedup table, a well-understood pattern on this team.

Defer Kafka. Its operational overhead and learning curve would consume weeks the team cannot spare, and its throughput advantages are irrelevant at our current and projected scale (~5K req/s after 10× growth is well within Redis Streams' single-node capability).

### Architecture Sketch

```
HTTP Request
    │
    ▼
Flask App ──X──→ smtplib / requests          ❌ BEFORE (synchronous, blocking)
              X──→ smtplib / requests


HTTP Request
    │
    ▼
Flask App ──────→ Redis (XADD to stream)     ✅ AFTER (async, 1–3 ms enqueue)
                      │
                      ▼
           Worker Pool (XREADGROUP)
                 │           │
                 ▼           ▼
           Email Svc     Webhook Svc  ──→ Dead-letter stream (XADD on max retries)
                 │           │
                 ▼           ▼
           Exactly-once dedup (PostgreSQL idempotency table for billing events)
```

---

## Consequences

### ✅ Pros

1. **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. Adding streams adds no new services, no new JVM processes, and no new attack surface.

2. **Fast time-to-value.** A senior engineer familiar with Redis can ship a working producer + consumer in one week. The two-week constraint is easily met.

3. **Team familiarity.** Every engineer on the team already uses Redis (session management, rate limiting). Streams use the same `redis-py` library. There is no learning cliff.

4. **Adequate throughput.** A single Redis node handles 100K+ operations/second. Our current peak of 500 req/s and even our 10× target of 5K req/s are two orders of magnitude below Redis Streams' ceiling. We will not be throughput-constrained.

5. **Rich consumer-group primitives.** `XREADGROUP` delivers each message to one consumer in a group. `XPENDING` + `XCLAIM` (or the newer `XAUTOCLAIM`) re-deliver messages from failed consumers. `XACK` prevents re-delivery on success. This covers retry with backoff, dead-letter routing, and worker scaling without any custom queuing logic.

6. **Natural WebSocket path.** Redis Streams + Pub/Sub coexist on the same instance. The WebSocket push feature planned for Q2 can subscribe to a notification stream or use Pub/Sub as a thin fan-out layer, avoiding a second broker.

7. **Simpler debugging and observability.** `XRANGE`, `XLEN`, and `XINFO` provide ad-hoc stream inspection from the Redis CLI — no dedicated tooling required.

8. **Lower blast radius.** A misconfigured Kafka cluster can lose data silently (e.g., unclean leader election, incorrect `min.insync.replicas`). A misconfigured Redis stream degrades predictably: the consumer falls behind, the stream length grows, and memory pressure alerts fire.

### ❌ Cons

1. **No native exactly-once delivery.** Redis Streams guarantees at-least-once delivery at the protocol level. For billing notifications, we must implement idempotent consumers with a dedup table (PostgreSQL `notification_dedup` with a unique constraint on `(event_id, notification_type)`). This is a well-known pattern but represents ~2 days of additional implementation and testing that Kafka would have provided natively via its idempotent producer + transactions.

2. **Memory-bound retention.** Kafka retains messages on disk; Redis retains streams in memory (by default). Under a sustained consumer outage, a backlog can consume enough RAM to trigger eviction. Mitigations: set `MAXLEN ~ 100K` on each stream, monitor consumer lag with `XINFO GROUPS`, and alert when lag exceeds a threshold. At 500 req/s, 100K messages represents ~3.3 minutes of backlog — adequate headroom given our sub-second consumer latency.

3. **No built-in stream partitioning.** Kafka partitions streams across brokers and rebalances consumers automatically. Redis Streams uses a single shard per stream. At 5K req/s this is irrelevant. If traffic grows another 10× (50K req/s), the Redis instance would need a larger memory allocation or a manual sharding strategy at the application layer (e.g., `stream:email`, `stream:webhook`, `stream:billing`). This is a future concern, not a current one.

4. **Smaller ecosystem.** Kafka ships with Kafka Connect, Schema Registry, KSQL, and extensive monitoring integrations (JMX, Burrow). Redis Streams has none of this. We compensate with application-level serialization (JSON schema validated at the producer and consumer, versioned with a `schema_version` field) and custom metrics exported from the worker process to CloudWatch/Datadog.

5. **No consumer rebalancing protocol.** If a Kafka consumer crashes, the group coordinator rebalances partitions to surviving consumers automatically. With Redis Streams, a crashed consumer's pending messages remain unclaimed until another consumer runs `XAUTOCLAIM` (or the timeout in `XREADGROUP` expires). The mitigation is straightforward: each worker runs a background `XAUTOCLAIM` loop every 30 seconds, and we run a minimum of 2 workers per stream for redundancy.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the gold standard for event streaming at scale. It offers:

- Native exactly-once semantics via idempotent producers and Kafka transactions, eliminating the need for a custom dedup layer.
- Disk-based retention with configurable time/size limits, making it resilient to long consumer outages without memory pressure.
- Automatic partition rebalancing and built-in consumer-group coordination.
- A mature ecosystem (Connect, Schema Registry, KSQL) that could support future event-sourcing use cases.

**Why it was rejected:**

- **Operational weight.** Kafka requires at least 3 broker nodes (JVM processes), ZooKeeper or KRaft for coordination, and careful tuning of JVM heap, OS page cache, and disk I/O. For a 6-person team with no dedicated infra engineer, this is a significant ongoing tax. One of this year's two cascading-failure incidents was caused by *one* slow webhook; introducing a JVM cluster with its own failure modes does not simplify the system.

- **Learning curve.** Zero team members have production Kafka experience. Budget does not cover Confluent Cloud. The team would need to learn broker configuration, topic partitioning, consumer rebalancing, monitoring (JMX, Burrow/Conduktor), and recovery procedures before shipping anything. This violates the two-week value constraint.

- **Over-provisioned for our scale.** Kafka is designed for 100K+ msg/s across dozens of partitions. Our 500 req/s peak and 5K req/s future target do not stress even a single-node Redis instance. Deploying Kafka at this scale means paying the operational cost of a nuclear reactor to heat a tea kettle.

- **Cost.** Self-hosted Kafka requires 3+ EC2 instances (at least `m6i.large` for reasonable performance). Managed services (MSK, Confluent) add $200–$1,000+/month. Redis Streams uses the existing Redis node with negligible additional memory (~100 KB for our stream metadata at current scale).

**Rejection rationale**: The exactly-once advantage is real, but the dedup table pattern is a 2-day implementation cost versus Kafka's ongoing operational tax. At our scale and team composition, Redis Streams wins on every axis except native EOS — and that gap is bridgeable with application-level code the team already knows how to write and test.

### RabbitMQ (Rejected passively)

RabbitMQ was not formally considered because it shares Kafka's operational-disadvantage profile (new infrastructure, new learning curve) without Kafka's throughput ceiling or ecosystem breadth. Additionally, RabbitMQ's queue-based model is less well-suited to the consumer-group/multi-subscriber pattern we need for email + webhook + future WebSocket consumers reading from the same stream. Redis Streams' single-stream/multi-consumer-group model maps more naturally to the notification fan-out use case.

### PostgreSQL LISTEN/NOTIFY (Rejected)

While PostgreSQL is already in the stack, `LISTEN/NOTIFY` has no persistence, no consumer groups, a single-channel bottleneck, and a 8 KB payload limit. It is useful for cache invalidation but cannot support retry, backoff, dead-letter routing, or exactly-once semantics. It fails every non-trivial requirement.

---

## Trade-off Summary

| Criterion                     | Kafka                          | Redis Streams              |
|-------------------------------|--------------------------------|----------------------------|
| Throughput (our scale)        | Overkill                       | ✅ Adequate (100K+ ops/s) |
| Exactly-once semantics        | ✅ Native (idempotent + txn)   | ⚠️ Requires app-level dedup |
| Message retention             | ✅ Disk-based, configurable    | ⚠️ Memory-bound, managed   |
| Consumer groups               | ✅ Built-in, auto-rebalance    | ✅ Built-in, manual claim   |
| Operational complexity        | ❌ High (JVM, ZK/KRaft, 3+ nodes) | ✅ Low (existing Redis)   |
| Time-to-value                 | ❌ 4+ weeks                    | ✅ 1 week                  |
| Team readiness                | ❌ Zero experience             | ✅ Existing Redis ops       |
| WebSocket integration path    | ⚠️ Requires separate infra    | ✅ Same Redis Pub/Sub      |
| 10× growth headroom           | ✅ Near-unlimited              | ✅ Adequate with sharding  |
| Ecosystem / tooling           | ✅ Rich (Connect, Registry)    | ❌ Minimal                  |

**Recommendation:** Redis Streams, with an application-layer dedup table for billing exactly-once semantics. This gives us the fastest path to a working, reliable notification pipeline — meeting the two-week constraint — while retaining headroom for 10× growth and a natural on-ramp to WebSocket push.
