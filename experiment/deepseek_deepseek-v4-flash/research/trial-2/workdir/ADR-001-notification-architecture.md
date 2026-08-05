# ADR-001: Async Notification Delivery — Adopt Redis Streams

## Status

Proposed (2026-08-05)

## Context

The notifications module sends emails and webhooks synchronously inside the HTTP request cycle. As the platform has grown this has produced four concrete failures (`system_context.md:18-25`):

1. **Request timeouts** — notification I/O blocks the response; average latency 800ms, spikes to 8s at peak.
2. **Silent failures** — a down email provider or webhook endpoint drops the notification with no retry and no dead-letter queue.
3. **Cascading failures** — twice this year a slow webhook endpoint exhausted the PostgreSQL connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, which the current path cannot provide.

The scaling target (`system_context.md:28-34`) is: decouple notifications from the request cycle; retry with exponential backoff; at-least-once for billing events with exactly-once where feasible; real-time WebSocket push within two quarters; and headroom for 10x traffic without re-architecting.

Constraints that bind the decision (`system_context.md:36-43`):

- Team of 6 (3 senior, 3 mid-level), **no dedicated infrastructure engineer**.
- **Redis is already in production** (session storage, rate limiting); **no Kafka experience on the team**.
- No more than **2 weeks of setup/migration** before delivering value.
- **Modest budget** — cannot afford managed Confluent Cloud at full scale today.
- Exactly-once semantics must be maintained for billing notifications.

**Load estimate (assumptions stated, not measured).** ~2M tasks/month at 22 business days × 8h ≈ 3.2 tasks/s average, with a stated peak of ~500 req/s. Notifications are a small multiple of requests (assignee email, watchers, webhooks), so the realistic notification peak is on the order of 10³/s; 10x growth puts the ceiling in the low 10⁴/s. Both candidate systems sit orders of magnitude above that — **raw throughput is not the binding constraint; operational complexity is.**

## Decision

**Adopt Redis Streams as the notification transport, running on a dedicated Redis instance** (separate from the session/rate-limiting cache) with AOF persistence and a replica.

Redis Streams is an append-only log data structure (Redis ≥ 5.0) with native consumer groups, explicit acknowledgment, and pending-entry tracking (https://redis.io/docs/latest/develop/data-types/streams/). The design:

- **Ingestion via PostgreSQL outbox.** The Flask app writes a notification intent into an `outbox` table *in the same transaction* as the task/billing state change. A relay worker publishes each row to a stream with an `event_id` idempotency key. This closes the dual-write gap: a crash between DB commit and stream publish cannot drop a notification, because the outbox row is still there.
- **One stream per notification class** (`billing`, `task.email`, `task.webhook`, `ws.push`), each consumed by its own consumer group. Streams allow multiple independent groups per stream, so email, webhook, and future WebSocket consumers can each read the same events at their own pace.
- **At-least-once delivery** is the native model: a message is delivered via `XREADGROUP`, processed, then removed from the group with `XACK`. If the consumer crashes before ack, the entry stays in the pending-entries list (PEL) and is redelivered to a healthy consumer via `XAUTOCLAIM`.
- **Retry with exponential backoff** is implemented in the consumer (track attempt count in the message, re-add to the stream or a retry stream with increasing delay), with a dead-letter stream after N attempts. The broker alone does not schedule delayed delivery in either candidate — this work is consumer-side in both designs.
- **Exactly-once for billing is achieved by consumer-side idempotency, not by the broker.** Each billing consumer dedupes on `event_id` against a unique-constrained dedupe table before calling the email/webhook provider, so a redelivered message produces one side effect. This is the only way to get exactly-once *outcomes* for external side effects with either system (see below), and Redis 8.6+ adds native producer-side dedup for this pattern (https://redis.io/docs/latest/develop/data-types/streams/idempotency/).
- **WebSocket push** (2-quarter target) reuses the same stream infrastructure: the WS gateway consumes `ws.push` and fans out to connected clients. No new transport is introduced.
- **Bounded retention** via `MAXLEN`/`XTRIM` so the log cannot grow unbounded; short-window replay (hours to days) is available via `XRANGE`.

**Why this choice is correct given the constraints.** The team constraint list is effectively a checklist for Redis Streams and a veto list for Kafka: we already operate Redis, the 2-week budget fits a data-type adoption that can ship in days, and the cost is incremental hardware — not a new cluster to run. Kafka's decisive technical strengths (native partitioning at scale, disk-backed retention, exactly-once *within* its own ecosystem) do not bind at our volume and do not cover our external side effects anyway.

**Escalation path (documented, not optional).** Revisit Kafka when any of these triggers fires: sustained stream volume approaching single-node Redis capacity; a requirement for multi-week replayable history inside the broker itself; multiple independent teams needing topic governance; or a need for native stream processing (joins/aggregations) at scale. The consumer code should be written behind a `NotificationTransport` interface so the stream backend can be swapped without rewriting producers.

## Consequences

### Pros

- **Zero new infrastructure.** Redis is already deployed and operated; Streams are a data type, not a service. The team's existing `redis-py` usage and runbook knowledge transfer directly.
- **Fits the 2-week constraint.** No cluster provisioning, no topic/partition planning, no rebalancing semantics to learn. The first end-to-end email flow can ship in days.
- **At-least-once is built in.** Consumer groups + PEL + `XACK` + `XAUTOCLAIM` give redelivery on crash, which is the exact "retry and don't drop" property the system lacks today. Multiple groups per stream give independent consumer speeds per notification class.
- **Ordering.** A single stream has a total order over all its entries (monotonically increasing IDs; `XADD` rejects out-of-order IDs). This is at least as strong as Kafka's per-partition ordering and needs no keying discipline.
- **Throughput headroom.** `XADD` is O(1) per entry; a single node comfortably handles the projected peak, including 10x. At our load, Redis Streams' single-node ceiling is not a practical limit.
- **Cheap.** Incremental memory/disk on already-running Redis hardware; no managed-broker bill.
- **WebSocket fit.** Pub/Sub and streams are both already in the stack, so the 2-quarter real-time push does not introduce a second transport or a second team skill.
- **Observability is adequate at this scale.** `XINFO STREAM/GROUPS/CONSUMERS` plus `XPENDING` expose lag and stalled consumers; simple to wire into existing dashboards.

### Cons

- **Durability is weaker than Kafka.** Redis replication is asynchronous; failover by Sentinel/Cluster is best-effort and "under certain specific failure conditions may promote a replica that lacks some data" (Redis Streams docs source, `streams/_index.md:928`). A primary loss can drop the most recent entries unless `WAIT`/durable AOF is configured. Mitigations: dedicated instance, AOF `appendfsync`, replica + `WAIT` for the billing stream. Kafka's ISR-committed writes are stronger here (Apache Kafka design doc, "Persistence" / design.md:191).
- **Horizontal scaling is manual.** A single stream is not automatically partitioned across instances ("if you really want to partition messages in the same stream into multiple Redis instances, you have to use multiple keys and some sharding system", `streams/_index.md:827`). Scaling past one node means application-level sharding by key, which sacrifices total ordering and complicates consumer groups. This is a real ceiling — just not one we approach at 10x.
- **Retention and replay are memory-bounded.** `MAXLEN` trimming bounds memory, but there is no disk-backed log, no per-topic compaction, no tiered storage. Long-window replay requires sizing `MAXLEN` generously or offloading consumed events to S3/PostgreSQL. Kafka's log retention + log compaction is genuinely better for historical replay.
- **No native exactly-once.** The broker provides at-least-once only; billing exactly-once is delivered by our idempotency-key + dedupe code (native dedup arrives only in Redis 8.6+). Kafka would require the same consumer-side idempotency for external side effects, so this is not a deficit relative to Kafka — but it is work we must build and test.
- **Shared-fate risk with the existing cache** unless separated. The session/rate-limit Redis is a cache with an ephemeral durability profile; notification streams are durable data. Mixing them couples availability and makes cache eviction policy dangerous. Hence the dedicated instance in the decision.
- **Smaller ecosystem.** No Kafka Connect, no stream-processing API, no mature lag/consumer-observability tooling. The features we would miss (connectors, exactly-once processing, multi-team governance) are not needed today.

## Alternatives Considered

**Apache Kafka — rejected.**

- **Throughput: overkill by orders of magnitude.** Kafka is a distributed broker engineered for very high throughput, fault tolerance, and durability (https://kafka.apache.org/intro). Our projected 10x peak is on the order of 10⁴ events/s — a load a single Redis node also handles with headroom to spare. The throughput advantage buys nothing we can use.
- **Ordering: not an advantage.** Kafka guarantees order per partition only (design.md:157); preserving cross-event order requires keying discipline. Redis Streams gives a total order per stream without that discipline. Comparable guarantees, less machinery.
- **Retention: Kafka wins, but we do not need it yet.** Kafka's disk-backed log with per-topic time/size retention and log compaction (design.md:370, 399) is the one area it is clearly superior. Our requirement is bounded short-term replay plus an audit trail; `MAXLEN` + S3 offload covers it. If a multi-month broker-side history requirement appears, that is a documented trigger to revisit.
- **Consumer groups: more mature, but a tax we would pay twice.** Kafka's groups auto-rebalance and assign partitions — genuinely nicer for many consumers. But it is also a failure-mode surface (rebalancing storms, offset management, lag semantics) that the team must learn from zero, with no Kafka experience today. Redis consumer groups are a concept the team can internalize in a day.
- **Exactly-once: does not apply to our problem.** Kafka's exactly-once semantics are real, but they hold when the *output is written to Kafka* — the consumer's offset and output are committed in the same transaction (design.md:203). The design doc is explicit that writing to an external system "the limitation is in the need to coordinate the consumer's position with what is actually stored as output" (design.md:205). Emails and webhooks are external; exactly-once delivery to them requires consumer-side idempotency with Kafka exactly as it does with Redis Streams. The requirement is therefore **neutral** between the two options — it removes Kafka's strongest technical argument rather than favoring it.
- **Operational complexity: decisive.** A 6-person team with no infra engineer and no Kafka experience would have to stand up and operate a broker cluster (brokers, disk sizing, topic/partition planning, rebalancing, upgrades, monitoring) to meet a 2-week delivery budget. Managed options (Confluent Cloud) are explicitly out of budget at full scale. Even a minimal self-hosted Kafka deployment — let alone running it in production under a 10x growth commitment — consumes the entire 2-week window before delivering a single notification. Redis Streams delivers the same functional requirements in days on infrastructure we already run.

*Scope note: the comparison was scoped to the two options requested. Other brokers (e.g., managed queues like SQS) were noted and set aside: they add a second vendor and weaker ordering/retention properties without addressing the constraints any better.*
