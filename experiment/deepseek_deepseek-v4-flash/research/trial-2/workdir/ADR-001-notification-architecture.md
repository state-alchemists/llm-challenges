# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

**Status:** Proposed

---

## Context

The Notifier subsystem is degrading production reliability. Notifications (email, webhooks) are sent synchronously inside the HTTP request cycle of a Python/Flask monolith (~50k LOC). At 500 req/s peak across 85,000 MAUs, this causes:

- **800ms average latency** with spikes to 8s, producing request timeouts.
- **Silent failures** — downstream email/webhook outages drop notifications with no retry or dead-letter queue.
- **Cascading failures** — two incidents this year where a slow webhook caused connection pool exhaustion, taking down unrelated features.
- **No delivery guarantees** — billing-critical notifications (trial expiry, payment failure) have zero reliability infrastructure.

We need to decouple notification dispatch from the HTTP request cycle and introduce retry mechanics, delivery guarantees, and a path toward real-time WebSocket push within the next two quarters. Traffic is expected to grow 10x over the architecture's lifespan.

**Constraints that narrow the design space:**

| Constraint | Impact |
|---|---|
| Team of 6 (3 senior, 3 mid-level), no dedicated infra engineer | Operational complexity must be low. No system that requires a specialist. |
| Redis already in production (session store, rate limiting) | Zero-infrastructure option exists — leverage what we run. |
| No Kafka experience on the team | Kafka carries a steep learning curve before first useful deployment. |
| ≤2 weeks to deliver value | Time-to-value is a hard deadline. |
| Budget modest; cannot afford Confluent Cloud | Managed Kafka (MSK, Confluent) is cost-prohibitive; self-hosted Kafka shifts cost to ops labor. |
| Exactly-once semantics required for billing notifications | Neither option provides this without application-layer support; both require idempotency keys. |

---

## Decision

**Use Redis Streams** as the notification backbone, replacing synchronous HTTP dispatch with an async producer-consumer pipeline.

Redis Streams maps cleanly onto the problem: notifications are produced by the Flask app (non-blocking `XADD`), consumed by a background worker pool (`XREADGROUP` with consumer groups), and retried via `XPENDING` / `XCLAIM` when consumers fail. The existing Redis instance is repurposed — no new infrastructure, no new stateful system to operate.

### How the requirements are met

| Requirement | Redis Streams Mechanism |
|---|---|
| Async decoupling | Flask app calls `XADD` (sub-millisecond), returns immediately. Worker process reads from stream. |
| Retry with exponential backoff | Unacknowledged messages remain in the Pending Entry List (PEL). Worker inspects `XPENDING`, checks delivery count, re-queues with backoff delay or moves to dead-letter stream after N failures. |
| At-least-once delivery | Consumer group acknowledgments (`XACK`). If a consumer crashes, `XCLAIM` reassigns its pending messages to another consumer. |
| Exactly-once (billing) | Producer assigns a unique idempotency key per event (e.g., `SHA256(user_id + event_type + timestamp)`). Consumer deduplicates against a Redis set with TTL. This pattern achieves *effectively once* without distributed transactions. |
| Real-time WebSocket push | Same stream feeds a WebSocket relay worker. No second pipeline. |
| 10x growth headroom | Current peak: 500 req/s ≈ ~2,000 notification events/s. Redis Streams on modest hardware handles **50,000–100,000 operations/s**. Headroom: 25–50x. |

### Implementation sketch

```
Flask App ──XADD──> Redis Stream (notifications)
                        │
            ┌───────────┼───────────┐
            │           │           │
        email       webhook     websocket
        worker      worker      relay
        (consumer   (consumer   (consumer
         group)      group)      group)
            │           │
     ┌──────┴──────┐    │
     │ retry (3x)  │    │
     │ dead-letter │    │
     └─────────────┘    │
                   ┌────┴────┐
                   │ retry   │
                   │ DLQ     │
                   └─────────┘
```

Dead-letter streams are separate Redis streams with `MAXLEN` trimming. Alerting fires on DLQ growth.

---

## Consequences

### Positive

1. **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. No ZooKeeper/KRaft quorum, no broker cluster, no new security group rules.
2. **Fast time-to-value.** A producer-consumer pipeline with retry can ship within one week. The ≤2-week constraint is easily met.
3. **Low operational burden.** The team already manages Redis. Redis Streams operations are Redis commands — no new tooling, no new runbooks for partition rebalancing or broker failure modes. A 6-person team with no infra specialist can own this.
4. **Plays well with existing Python stack.** `redis-py` has mature Streams support. No new client dependency beyond what is already in `requirements.txt`.
5. **Consumer groups are first-class.** `XREADGROUP`, `XACK`, `XPENDING`, and `XCLAIM` form a complete consumer-group protocol comparable to Kafka's, without Kafka's partition-management overhead.
6. **Natural path to WebSocket push.** The same stream feeds a WebSocket relay consumer. No architectural detour.

### Negative

1. **No native exactly-once.** Neither Redis Streams nor Kafka provides true exactly-once without application help. Redis requires the caller to implement idempotency-key deduplication. This is well-understood and low-risk but adds ~50 LOC to the consumer.
2. **Memory-bound retention.** Redis streams live in RAM. Long-term event replay or audit-trail retention requires periodic dumping to object storage (S3) or PostgreSQL. Kafka stores to disk and retains by configurable policy natively.
3. **Single-node bottleneck.** Redis is single-threaded for data operations. Partitioning across Redis Cluster nodes is possible but adds complexity. For 5,000 req/s (10x growth) this is not a concern — but if traffic exceeds ~50,000 events/s, the single-node architecture becomes the ceiling.
4. **No native stream repartitioning.** Kafka allows repartitioning a topic (at a cost). Redis Streams require application-level sharding if consumers fall behind on a single stream at scale.

---

## Alternatives Considered

### Apache Kafka

Rejected for three reasons that interact destructively with the team's constraints.

**Operational complexity exceeds team capacity.** Kafka is a distributed system that requires careful tuning at every layer: broker JVM heap sizing, partition count vs. replication factor, ISR configuration, log compaction vs. retention policies, consumer rebalancing protocols, ZooKeeper or KRaft quorum health. A self-hosted Kafka deployment demands dedicated operational attention. With 6 engineers, no dedicated infra role, and zero Kafka experience, the risk of a misconfigured cluster causing data loss or availability incidents is unacceptably high.

**Managed Kafka is out of budget.** AWS MSK pricing at the low end starts around $200/month for a three-broker cluster, but throughput-appropriate sizing for future growth (storage, IOPS) pushes into the $600–1,200/month range. Confluent Cloud adds feature markup. Against a "modest budget" constraint, this cost is difficult to justify when Redis Streams ($0 additional) solves the same problem.

**Throughput overkill with a slower time-to-value.** Kafka excels at 100k+ messages/second across distributed consumers with strict partitioning guarantees. Our peak is 500 req/s, projected to 5,000 req/s. Kafka's complexity is a cost paid upfront for capacity that will not be needed for years, if ever. The team needs a working notification pipeline in ≤2 weeks. A production-grade Kafka deployment (cluster provisioning, topic design, schema registry, consumer-group tuning, monitoring for consumer lag, offsets, and broker health) requires at minimum 3–4 weeks for a team learning it from scratch.

**Why not use both?** Running Redis Streams as the primary notification bus (for speed, low ops, existing infra) with Kafka as an audit/analytics sink downstream is a viable future architecture, but premature today. When the team grows or traffic exceeds Redis's single-node ceiling, a separate event pipeline can be introduced for the analytics use case without displacing Redis Streams for notifications.

---

## Recommendation

Redis Streams, with the following migration sequence:

1. **Week 1:** Introduce a notification stream. Flask app writes to the stream via `XADD` instead of calling email/webhook clients synchronously. Deploy a single consumer worker that drains the stream and performs the existing dispatch logic. This alone eliminates request-timeout and connection-pool-exhaustion incidents.
2. **Week 2:** Add consumer groups (`email-worker`, `webhook-worker`), retry logic with `XPENDING` inspection, and a dead-letter stream. Add idempotency-key deduplication for billing events.
3. **Quarter 2:** Add the WebSocket relay consumer from the same stream. Evaluate whether audit-trail events should be fanned out to a long-term store (S3/PostgreSQL) at this point.

This delivers value within the 2-week deadline, respects the team's skill profile, reuses existing infrastructure, and provides headroom to 50x current traffic before hitting architectural limits.
