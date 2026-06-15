# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

**Status:** Proposed

---

## Context

The notifications module (emails, webhooks) currently runs synchronously inside the Flask HTTP request cycle. This causes request timeouts (800 ms average, 8 s spikes), silent failures with no retry, connection-pool exhaustion cascading into unrelated features, and zero delivery guarantees for billing-critical events.

The system serves 85,000 MAU creating ~2M tasks/month at a peak of 500 req/s. The team of six (three senior, three mid-level) must ship within two weeks, and the chosen solution must support 10× traffic growth.

We evaluated two candidate technologies for the async message broker layer.

---

## Decision

**Use Redis Streams as the notification message broker.**

Redis Streams gives us async decoupling, consumer groups with at-least-once delivery, retry via pending-entry management (XPENDING/CLAIM), and a path to WebSocket push — all using infrastructure already running in production. The operational cost is negligible compared to standing up a separate Kafka cluster, and the team can ship within the two-week window.

### Why not Apache Kafka

Kafka is the stronger technology on paper — durable log storage, strict partition ordering, replay from any offset, and higher throughput — but it is the wrong fit for this team, this timeline, and this traffic profile:

1. **Operational overhead.** A production Kafka deployment requires at minimum a 3-broker cluster plus KRaft/ZooKeeper nodes. Every broker needs JVM tuning, disk sizing for retention, partition-rebalance monitoring, and consumer-lag alerting. A team of six with no dedicated infra engineer and no Kafka experience cannot absorb this burden while also building the notification service itself.

2. **Two-week delivery constraint fails.** Provisioning, securing, tuning, and integrating Kafka in production takes two weeks minimum for an experienced team — longer for one learning it from scratch. Redis Streams can be production-ready in two days.

3. **Overkill at current scale.** Kafka's sweet spot is 100k+ messages/second across multiple consumers with replay and long-term retention. At 500 req/s (5,000 at 10×), Redis Streams handles the load trivially. Redis benchmarks show 100k+ ops/s on modest hardware — a 20× safety margin over the 10× target.

4. **Exactly-once is an application concern, not a broker concern.** Kafka's exactly-once semantics (EOS via transactions) guarantees exactly-once *within Kafka* — it does not guarantee that the email provider or webhook endpoint processes the event exactly once. The only practical path to exactly-once for billing notifications is idempotent consumers with a deduplication table, regardless of broker choice. Redis Streams + idempotent consumer + `event_id` dedup in PostgreSQL = effectively-once delivery, which is indistinguishable from Kafka EOS at the application layer.

5. **Budget.** Managed Kafka (Confluent Cloud) is cost-prohibitive at this stage. Self-hosted Kafka trades budget for team time — the wrong trade when time is the tighter constraint.

### Why Redis Streams fits

*Already in the stack.* Redis runs in production for session storage and rate limiting. Adding Streams requires no new EC2 instances, no new credentials, no new monitoring dashboards, no new on-call runbooks. The team deploys code, not infrastructure.

*Familiar primitives.* The Python team already uses `redis-py`. Redis Streams consumer groups map cleanly to `XREADGROUP`, `XPENDING`, `XCLAIM`, and `XACK` — a well-documented API with published patterns for retry logic and dead-letter queues. No JVM, no schema registry, no new client protocol.

*Natural fit for WebSocket push.* Redis Pub/Sub is already available in the same Redis instance. A consumer worker reads from a notification stream and publishes to a WebSocket channel. Kafka would require either a separate WebSocket gateway service or Kafka Connect — both adding deployment complexity.

*Memory is not the bottleneck people fear.* At 5,000 req/s with a 24-hour retention window and ~5 KB per notification message, the stream uses ~2 GB of RAM — a fraction of what a production Redis instance is typically provisioned for. Acknowledged messages are trimmed immediately via `XTRIM` or `MAXLEN`, keeping working memory low.

---

## Consequences

### Positive

- **Async decoupling.** The HTTP handler writes a stream entry (low single-digit ms) and returns. Notification delivery is handled by background consumer workers. Request latency drops from 800 ms to <50 ms.
- **At-least-once delivery.** Consumer groups with XPENDING and auto-claim give automatic retry. Workers that crash mid-processing are reassigned to another consumer after the pending-entry timeout elapses.
- **Retry with exponential backoff.** A dead-letter stream (e.g., `notifications:dlq`) collects entries that exceed the retry limit. A scheduled job or manual process can inspect and replay them.
- **Exactly-once for billing.** Each billing event carries a unique `event_id` (e.g., `UUIDv7`). The consumer checks a dedup table (`notification_dedup(event_id VARCHAR PRIMARY KEY, processed_at TIMESTAMP)`) before processing. Duplicate deliveries from auto-claim or consumer crashes are silently dropped. Combined with at-least-once delivery from the stream, this yields effectively-once semantics.
- **No new infrastructure.** Single additional process (consumer worker). Same Redis, same deploy pipeline, same monitoring.
- **WebSocket path.** Consumer can `XREAD` the notification stream and publish to Redis Pub/Sub, which a WebSocket server subscribes to. No new message broker needed.
- **10× headroom.** Redis handles 100k+ ops/s on a 2 vCPU / 4 GB instance. Memory is the scaling axis — if needed, increase instance size or shard notification streams by tenant ID.

### Negative

- **Memory-bound retention.** Unlike Kafka, which writes to disk, Redis Streams live in RAM. Long retention windows or bursty unacknowledged messages could pressure memory. Mitigation: set `MAXLEN ~ 100000` per stream, trim aggressively, and alert on pending-entry count exceeding a threshold.
- **No built-in ordering across partitions.** Kafka guarantees strict order within a partition. Redis Streams guarantee order within a single stream, but if you shard across multiple streams (e.g., per tenant), cross-stream ordering is lost. For notifications this is acceptable — email ordering is not a correctness constraint. If it becomes one, route all events through one stream and scale consumers within that stream's consumer group.
- **Smaller ecosystem.** Kafka has Kafka Connect, Kafka Streams, schema registry, and a vast connector ecosystem. Redis Streams has the core primitives and community patterns. For a team of six building one notification subsystem, the ecosystem gap is irrelevant — there is no plan to integrate with a data lake, run stream processing, or maintain a schema governance board.
- **Billing-event gap window.** Between a consumer crashing and the auto-claim timeout reclaiming its pending entries, there is a configurable window (default: minutes) where a billing notification could be delayed. Mitigation: set `XPENDING` claim timeout to 30 seconds, and use a periodic background poll to retry pending entries proactively rather than waiting for the timeout.
- **Learning curve.** Redis Streams are new to the team. However, the API surface is small (~10 commands) and the redis-py client documentation is good. This is a days-long learning curve versus the weeks-long Kafka learning curve.

---

## Alternatives Considered

### Apache Kafka (rejected)

Kafka was rejected for the reasons detailed above: operational complexity exceeds the team's capacity, two-week deadline is unachievable, throughput is overkill for the traffic profile, and the budget for managed Kafka is unavailable. The sole technical advantage Kafka holds over Redis Streams — durable disk-based retention with unlimited replay — does not justify the operational cost for this use case. Notifications are ephemeral: they are delivered, acknowledged, and can be discarded. Long-term replay of weeks-old notifications has no product requirement today.

A future migration to Kafka is possible if the system outgrows Redis (e.g., >50,000 req/s or multi-TB retention needs), but that is a high-class problem the team does not face today.

### RabbitMQ (not formally evaluated)

RabbitMQ was not evaluated as a primary option because the team does not run it in production and the constraint to deliver within two weeks eliminates any technology requiring new infrastructure and operational training. RabbitMQ shares many of Kafka's disadvantages (new cluster, new on-call burden) while offering weaker ordering guarantees and no native stream replay. It would rank below both Redis Streams and Kafka for this use case.

---

## Implementation Outline

| Step | Effort | Detail |
|------|--------|--------|
| 1. Define stream schema | 1 day | Event envelope: `event_id`, `type`, `tenant_id`, `payload`, `retry_count`, `created_at` |
| 2. Write producer integration | 2 days | Replace sync notification calls with `XADD` in the Flask handler |
| 3. Write consumer worker | 3 days | Python process using `XREADGROUP` + `XPENDING` loop; dead-letter routing; exponential backoff |
| 4. Add dedup table for billing events | 1 day | `notification_dedup(event_id PK, processed_at)` with idempotent consumer check |
| 5. Deploy and monitor | 2 days | One additional process per web server; existing Redis monitoring alerts; add pending-entry metric |
| **Total** | **9 days** | Within the 2-week constraint with buffer |

The consumer worker runs as a background process on each of the four web servers (four consumers in the group). For 10× scale, spin up dedicated worker instances independent of the web tier — Redis Streams consumer groups support dynamic membership without downtime.
