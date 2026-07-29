# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, 500 req/s peak) currently handles all notifications — emails, webhooks, and soon WebSocket pushes — synchronously inside the HTTP request cycle. This has caused request timeouts (800ms avg, 8s spikes), silent delivery failures with no retry or dead-letter queue, two cascading outages from slow webhook endpoints exhausting the connection pool, and zero delivery guarantees for billing-critical notifications.

We need to decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (with effectively-once for billing events), support real-time WebSocket push within two quarters, and absorb 10x traffic growth without re-architecting.

Key constraints:
- **6-person engineering team** (3 senior, 3 mid-level), no dedicated infrastructure engineer
- **Redis already in production** for sessions and rate limiting — team has operational familiarity
- **No Kafka experience** on the team
- **2-week ceiling** before the migration must deliver observable value
- **Modest budget** — managed Confluent Cloud at scale is not affordable today
- **Exactly-once semantics required** for billing notifications

Peak notification throughput is estimated at ~500 notifications/s today, targeting ~5,000/s at 10x growth. Notification payloads are small (JSON task events, ~1–5 KB). Retention needs are short — once consumed and acknowledged, messages can be discarded (hours, not weeks).

## Decision

**Use Redis Streams as the notification subsystem's message broker.**

Redis Streams satisfies every functional requirement — async decoupling, consumer groups, at-least-once delivery, retry via pending-entry tracking — within our operational and temporal constraints. Kafka is architecturally superior for high-throughput, long-retention event streaming, but those are not our constraints. Our constraints are team size, time-to-value, budget, and operational simplicity. Redis Streams wins decisively on those axes, and the technical gaps (notably exactly-once for billing) are addressable at the application layer — as they would be with Kafka anyway.

## Consequences

### Pros

1. **Fast time-to-value.** The team already operates Redis in production. Adding a stream is a configuration change, not a new distributed system. First async notification can ship in days, not weeks — well within the 2-week constraint.

2. **Consumer groups out of the box.** `XREADGROUP` with `XACK` provides at-least-once delivery and group-based fanout. Multiple notification workers (email, webhook, WebSocket) each get their own consumer group, processing the same stream independently — exactly the topology we need.

3. **Built-in retry and pending-entry tracking.** `XPENDING` and `XCLAIM` let a worker reclaim messages from a failed consumer after a timeout. This replaces the current "silent drop" behavior with automatic retry. Exponential backoff is implemented at the consumer by delaying `XCLAIM` re-processing based on delivery count stored in the message.

4. **Sufficient throughput and ordering.** A single Redis instance handles 100K+ ops/s. At our target of 5,000 notifications/s, Redis is not the bottleneck. Within a single stream, `XADD` preserves insertion order — notifications for a given task are processed in order by any single consumer group.

5. **Dead-letter via application pattern.** After N retry attempts, the consumer moves the message to a `notifications:dead` stream and alerts. This is not built into Redis, but the pattern is straightforward and fully under our control.

6. **Operational simplicity.** No new distributed system to learn, monitor, or staff for. Redis is already on-call. No ZooKeeper/KRaft cluster, no partition rebalances to debug, no new page-runbook to write.

7. **WebSocket path is natural.** A lightweight consumer group for WebSocket push reads from the same stream — no separate fanout mechanism required. This integrates cleanly within the 2-quarter timeline.

8. **Cost.** Redis is already paid for. No additional infrastructure spend.

### Cons

1. **No native exactly-once semantics.** Redis Streams provides at-least-once; a consumer can see a duplicate if it crashes after processing but before `XACK`. **Mitigation**: For billing notifications, implement idempotent consumers using a PostgreSQL deduplication table (`notification_id` with a `UNIQUE` constraint). The consumer INSERTs the notification ID before processing; a duplicate is rejected at the database level. This achieves effectively-once delivery for billing events. Note: Kafka's exactly-once semantics (EOS) addresses Kafka-internal transactionality — ensuring atomic produce-consume across partitions — not the idempotency of side effects like sending an email. For our use case, application-level idempotency is required regardless of broker choice.

2. **Memory-bound retention.** Redis holds stream data in memory. `MAXLEN` or `MINID` trimming is required to bound stream size. At 5,000 msg/s × 5 KB average × 1-hour retention, that is ~90 MB — well within a modern Redis instance. But retention beyond a few hours is impractical without offloading. **Mitigation**: Set `MAXLEN ~ 500000` (approximate trimming for performance). For audit/replay needs beyond the retention window, write consumed notifications to PostgreSQL before `XACK`. This is the pattern we want anyway for billing audit trails.

3. **Single-node availability risk.** Our current Redis is a single instance (not a cluster). A Redis outage blocks notification processing. **Mitigation**: Enable Redis persistence (AOF) and configure the managed Redis replica for automatic failover (AWS ElastiCache or equivalent). This is consistent with our current Redis availability posture for sessions — a brief notification delay during failover is acceptable; data loss is not (AOF addresses this).

4. **Less mature consumer group model than Kafka.** Redis consumer groups lack automatic partition rebalancing and lag monitoring built into the protocol. **Mitigation**: Implement a lightweight health-check loop in the worker that uses `XPENDING` to detect and claim stalled messages. Add a `/metrics` endpoint exposing `XLEN` and `XPENDING` counts for monitoring. This is ~50 lines of Python, not a fundamental limitation.

5. **Single-threaded per shard.** A single Redis shard processes commands sequentially. At 5,000 msg/s, this is not a constraint (each `XADD` is sub-millisecond), but it becomes relevant at significantly higher scales. **Mitigation**: If we exceed ~50K msg/s (a 100x growth factor), shard by notification type across multiple streams (`notifications:billing`, `notifications:webhook`, etc.) or migrate to Redis Cluster. The 10x growth target (5,000 msg/s) is well within a single-shard capacity.

6. **No native schema registry.** Kafka has Confluent Schema Registry for enforcing message contracts. Redis Streams has no equivalent. **Mitigation**: Enforce message schema at the producer (Pydantic models in the Flask app) and version messages with a `schema_version` field. This is lightweight and sufficient for a single-producer, few-consumer topology.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event streaming platform and is objectively more capable than Redis Streams for large-scale, long-retention, multi-consumer event pipelines.

**Reasons Kafka was considered favorably:**
- True partition-based parallelism with automatic consumer rebalancing
- Durable, disk-based storage with configurable retention (days to weeks to forever)
- Exactly-once semantics (EOS) via idempotent producers and transactional consumers
- Mature ecosystem: Kafka Connect, Schema Registry, ksqlDB, extensive monitoring tooling
- Proven at millions of messages/second

**Reasons Kafka was rejected for this decision:**

1. **Operational complexity exceeds team capacity.** A production Kafka deployment requires broker configuration, partition strategy, replication factor tuning, monitoring (lag, under-replicated partitions, ISR), and on-call expertise. Our team has zero Kafka experience and no dedicated infrastructure engineer. The 2-week constraint makes this a non-starter — standing up production Kafka alone (even managed) takes longer than our entire allotted migration window when you include on-call readiness, runbooks, and incident-response familiarity.

2. **Budget.** Managed Kafka (Confluent Cloud, AWS MSK) starts at ~$0.10/GB ingested plus per-partition costs. At our scale this is manageable today, but the constraint explicitly states we cannot afford managed Confluent at full scale. Self-managed Kafka on EC2 shifts the cost to engineering time — our scarcest resource.

3. **Overkill for the use case.** Our throughput is ~500 msg/s today, targeting 5,000 msg/s. Our retention need is hours, not weeks. Our consumer topology is 3–4 groups (email, webhook, WebSocket, possibly billing). Kafka is designed for orders of magnitude more complexity than this. Deploying it would add operational overhead with no corresponding functional benefit over Redis Streams for this topology.

4. **Exactly-once is not the differentiator it appears to be.** Kafka's EOS ensures that Kafka-internal consume-transform-produce cycles are atomic. It does *not* guarantee that an external side effect (sending an email, calling a webhook) happens exactly once. For our billing notification requirement — "the recipient gets exactly one email" — we need application-level idempotency (deduplication table, idempotency key) regardless of broker. Kafka reduces the *probability* of redelivery but does not eliminate it for side-effecting consumers. The same PostgreSQL deduplication pattern that makes Redis Streams "effectively once" is required with Kafka too. Claiming Kafka gives you exactly-once email delivery is a category error.

5. **Migration risk.** Adding Kafka to our stack introduces a new failure domain before we've proven the async notification pattern works. Redis Streams lets us validate the architecture (consumer groups, retry logic, dead-letter, monitoring) on infrastructure we already trust. If we outgrow Redis Streams at 50K+ msg/s or need multi-week retention, Kafka can be introduced as a second migration — this time with team experience in async notification patterns and a clear operational model to replicate.

**When Kafka would be the right choice:** If we were building a general-purpose event bus for cross-domain event sourcing, needed multi-week retention for replay, or expected 100K+ msg/s, Kafka's strengths would outweigh its operational cost. That is not our current situation, and choosing it now would trade delivery speed and operational simplicity for capability we cannot use yet.

---

*This decision should be revisited if notification throughput exceeds 50,000 msg/s, if retention requirements extend beyond 24 hours, or if the team grows to include a dedicated infrastructure engineer with Kafka expertise.*