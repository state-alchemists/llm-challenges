# ADR-001: Notification Subsystem Architecture — Redis Streams

**Status:** Proposed

---

## Context

The Notifier subsystem handles email and webhook delivery for task updates, assignments, and completions in a SaaS project management platform. It currently runs synchronously inside the HTTP request cycle of a Python/Flask monolith, causing four systemic problems:

1. **Request timeouts** — blocking sends add 800ms average latency, spiking to 8s at peak.
2. **Silent failures** — downstream provider failures drop notifications with no retry or dead-letter queue.
3. **Cascading failures** — slow webhook endpoints exhaust connection pools, taking down unrelated features (two incidents this year).
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") require exactly-once delivery and have none.

The platform serves 85k MAU, peaks at ~500 req/s, and creates ~2M tasks/month. The engineering team is 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We already run Redis for session storage and rate limiting. No team member has Kafka experience.

The target architecture must decouple notifications from HTTP, support retry with exponential backoff, provide at-least-once (exactly-once for billing events), handle 10x growth without re-architecting, and enable real-time WebSocket push within 2 quarters. The solution must ship value within 2 weeks of starting work.

---

## Decision

**Use Redis Streams** as the notification backbone. This is a pragmatic choice that maximizes value delivered within the team's size, skillset, and timeline constraints, while preserving sufficient headroom for the 10x growth target.

We will achieve exactly-once semantics for billing notifications via consumer-side idempotency (event UUID deduplication in PostgreSQL), rather than relying on a broker-level transactional guarantee.

### Architecture sketch

```
HTTP Request → Flask handler → XADD event to Redis Stream
                                     │
                            ┌────────┴────────┐
                            │  Consumer Group  │  (at-least-once via XREADGROUP + XACK)
                            └────────┬────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                 │
              Email Sender     Webhook Sender    Dead-Letter Queue
              (retry+backoff)  (retry+backoff)   (separate stream key)
                    │                │
                    │     Dedup check: event_uuid IN (
                    │       SELECT 1 FROM delivered_events WHERE id = %s
                    │     )
                    │     INSERT INTO delivered_events (id, delivered_at)
                    └────────────────┘
```

Every billing event carries a `dedup_key` (deterministic UUID derived from event type + entity ID + timestamp). The consumer checks a `delivered_events` table before acting. This gives exactly-once delivery without requiring broker-level transactions.

---

## Consequences

### Pros

1. **Zero new infrastructure.** Redis is already deployed, monitored, and understood. Adding streams uses the same `redis-py` library already in the codebase. Estimated time to first notification flowing through the new path: 3–5 days.

2. **Fast time-to-value.** A working prototype (enqueue → consume → send email with retry) can ship within one sprint. The team ships Redis-backed code regularly — no learning curve overhead.

3. **Operational simplicity.** A 6-person team with no infra specialist can manage Redis Streams alongside existing cache duties. No ZooKeeper/KRaft clusters, no broker topology decisions, no partition reassignment tooling. Configuration is a few `XADD`/`XREADGROUP` commands and a reasonable `MAXLEN` policy.

4. **Adequate throughput for 10x growth.** At 10x the current peak, we expect ~5,000 events/s. A single Redis instance handles 100k+ ops/s for stream operations. With Redis Cluster, this scales to hundreds of thousands per second. Headroom is comfortable.

5. **Natural fit for WebSocket push.** The consumer group pattern maps cleanly to fanning events out to multiple WebSocket server processes. Redis Pub/Sub can bridge stream events to connected clients with sub-millisecond latency. This aligns with the 2-quarter WebSocket roadmap without introducing another piece of infrastructure.

6. **Consumer groups with pending-entry recovery.** Redis 5.0+ consumer groups provide `XPENDING` for tracking unacknowledged messages and `XCLAIM` for reassigning them to healthy consumers after a timeout — a workable retry and recovery primitive without external infrastructure.

7. **Eventual migration path to Kafka.** The stream → consumer-group abstraction is shared between Redis Streams and Kafka. If the team grows, traffic exceeds Redis capacity, or a stricter exactly-once requirement emerges, the producer interface changes by one import and the consumer interface is conceptually identical.

### Cons

1. **No native exactly-once delivery.** Redis Streams guarantees at-most-once or at-least-once depending on acknowledgment discipline. There is no transactional producer or idempotent-write feature comparable to Kafka's `enable.idempotence=true`. Exactly-once *delivery* must be constructed at the consumer layer (idempotent receiver pattern), which adds a small per-event deduplication query and a `delivered_events` table in PostgreSQL.

   **Mitigation:** The idempotent-consumer pattern is well-understood and production-proven. The dedup table can be pruned aggressively (TTL on `delivered_at` older than 7 days). Billing event volume is low (< 5% of total notifications), so the overhead is negligible.

2. **Memory-bound retention.** Redis is an in-memory store. Stream entries consume RAM. At 10x traffic, retaining hours of backlog for slow consumers requires intentional sizing. A 24-hour buffer of 5,000 events/s × 1 KB/event ≈ 430 MB of RAM — manageable but requires monitoring.

   **Mitigation:** Use `MAXLEN ~ <N>` (approximate trimming) to bound stream size. Use a dedicated Redis instance or a separate logical database for streams so notification data doesn't compete with cache working memory. Monitor `used_memory_streams` in production.

3. **No built-in dead-letter queue.** Redis Streams has no native DLQ concept. Consumers that exhaust their retry budget (e.g., after 10 attempts with exponential backoff) must be routed to a separate stream key manually by the application code.

   **Mitigation:** This is ~50 lines of Python. On final retry failure, `XADD` the event to a `notifications:dlq` stream with the original event payload and a `failure_reason` field. Alert on DLQ stream length in Datadog/Prometheus.

4. **No built-in rebalancing for scaled consumers.** When adding or removing consumers in a group, Redis requires manual partition (stream shard) assignment. It does not auto-rebalance like Kafka's cooperative sticky assignor.

   **Mitigation:** At the current scale (and 10x), a single stream per notification type with 2–3 consumer processes per stream is sufficient. The manual rebalance is a configuration deploy, not an operational burden at this size. If scale demands it later, partition by `task_id % N` and route producers to the correct shard — this is more work than Kafka's auto-rebalance but is a known pattern.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka excels in the areas where Redis Streams is weakest — native exactly-once semantics, long-term disk-based retention, automatic consumer rebalancing, and a mature dead-letter and retry ecosystem. It is the correct choice for a team with infrastructure headcount and Kafka experience.

**Why it was rejected:**

1. **Two-week delivery constraint is infeasible.** Standing up a production Kafka deployment requires: provisioning and tuning 3+ brokers, configuring KRaft (ZooKeeper is deprecated but still in wide use), setting up monitoring on broker/consumer lag/metrics, designing the partitioning strategy, writing producer/consumer code against an unfamiliar API (`confluent-kafka-python` or `kafka-python` with different guarantees), and testing under load. A team with zero Kafka experience cannot do this reliably in two weeks. Four to six weeks is a realistic estimate.

2. **Operational overhead exceeds team capacity.** A 6-person team with no dedicated infrastructure engineer cannot absorb the ongoing maintenance of a Kafka cluster — broker upgrades, partition rebalancing, consumer lag triage, disk sizing, and the JVM tuning that self-hosted Kafka requires. Managed Confluent Cloud removes the ops burden but costs $2,000–$5,000+/month at the projected throughput, which contradicts the "modest budget" constraint.

3. **Kafka's strengths are overkill for current scale.** At 500 req/s (5,000 at 10x), a single Redis instance handles the throughput with headroom to spare. Kafka's horizontal partitioning, multi-replica fault tolerance, and replay-from-epoch capabilities are solving problems this system does not yet have. The team pays the complexity tax today for benefits it won't realize for 1–2 years — if ever.

4. **Existing Redis expertise accelerates delivery.** The team already writes Redis-backed code. Adopting Kafka means learning a new protocol, a new client library, a new deployment model, and a new failure vocabulary (ISR, unclean leader election, min.insync.replicas). That learning curve has a real opportunity cost for a team of 6.

**When to revisit Kafka:**

- Team grows to 10+ engineers, or hires an infrastructure/SRE role.
- Throughput exceeds ~100k events/s, or retention requirements exceed Redis memory bounds economically.
- The idempotent-consumer exactly-once pattern proves insufficient for billing audits (unlikely, but would be discovered within weeks of production use).
- The team adds a feature requiring long-term stream replay (e.g., event sourcing or audit log replay beyond a few days of retention).

At that point, Kafka (or a managed alternative like WarpStream/Redpanda) should be re-evaluated. The stream abstraction and consumer-group semantics are shared, so the migration cost is moderate — a producer-side adapter and a consumer-side adapter, not a full rewrite.
