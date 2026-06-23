# ADR-001: Notification Subsystem — Async Processing Architecture

**Status:** Proposed

---

## Context

The notifier subsystem of our SaaS project management platform currently sends emails and webhooks synchronously inside the HTTP request cycle. As the platform has grown to 85,000 MAU and ~2M tasks/month, this approach has broken down:

- **Request timeouts**: Average 800 ms latency, spiking to 8 s during peak hours, because response blocks on external I/O.
- **Silent failures**: Unreachable email providers or webhook endpoints drop the notification with no retry or dead-letter queue.
- **Cascading failures**: Two incidents where a slow webhook consumed all connection pool workers, taking down unrelated features.
- **No delivery guarantees**: Billing-critical notifications (trial expiry, payment failure) need at-least-once or exactly-once delivery, but the current system guarantees nothing.

### Scaling Target

1. Decouple notifications from the HTTP request cycle.
2. Support retry with exponential backoff.
3. Guarantee at-least-once delivery for all notifications; exactly-once for billing events.
4. Add real-time WebSocket push within two quarters.
5. Handle 10× current traffic without re-architecting.

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid), no dedicated infrastructure engineer.
- **Existing infrastructure**: Redis already in production (session storage, rate limiting). No Kafka experience on the team.
- **Timeline**: Must deliver value within two weeks of setup/migration work.
- **Budget**: Modest — managed Confluent Cloud at full scale is out of reach.
- **Exactly-once requirement**: Billing notifications must not be duplicated or lost.

---

## Decision

**Adopt Redis Streams** for the notification queue substrate.

Redis Streams will serve as the buffer between the HTTP request handler and a pool of background workers that dispatch emails, webhooks, and (future) WebSocket pushes. The HTTP handler writes a notification event to a stream; a set of consumer groups processes it, tracks pending messages, and retries on failure via the Pending Entry List (PEL).

### Architecture Sketch

```
HTTP Request
    │
    ▼
Flask handler ──X── (no longer sends notifications inline)
    │
    ├─► XADD notification:email   * stream
    ├─► XADD notification:webhook * stream
    └─► XADD notification:billing * stream
              │
              ▼
   Consumer workers (per stream, per consumer group)
              │
              ├─► SMTP / SendGrid API
              ├─► HTTP POST to webhook URL
              └─► Redis Pub/Sub → WebSocket gateway (future)
```

Each stream is scoped to a notification type so billing events (which demand stronger guarantees) route through a dedicated consumer group with stricter retry and dead-letter logic.

---

## Consequences

### Positive

1. **Async decoupling achieved in days, not weeks.** Adding streams to an existing Redis instance is a configuration change, not a new cluster. We can have a working prototype in one day and production traffic within the two-week constraint.

2. **Team can own it.** The team already operates Redis for session storage and rate limiting. Streams reuse the same connection pool, authentication, and monitoring. Zero new infrastructure to learn or maintain.

3. **Consumer group semantics fit the use case.** Redis consumer groups track per-consumer delivery offsets with a PEL (Pending Entry List) that records messages delivered but not acknowledged. A worker crash leaves the message in the PEL; a separate consumer or a recovery process can claim and retry it (`XAUTOCLAIM`). This gives us at-least-once delivery out of the box.

4. **Exactly-once for billing is achievable with idempotency keys.** No message broker can guarantee exactly-once delivery to an *external* system (email provider, webhook endpoint) — the external system can always fail after processing but before acknowledging. Redis Streams + consumer-side idempotency (deduplication via `XADD`-generated message IDs, stored in a Redis set per billing event) achieves the same practical guarantee as Kafka's transactional API, with less complexity.

5. **Natural path to WebSocket push.** Redis Pub/Sub already supports publish-subscribe patterns. The same consumer workers that dispatch outbound emails can `PUBLISH` to channels consumed by a WebSocket gateway. This avoids introducing a second message broker when we add real-time push.

6. **Scales to the target.** Current peak is ~500 req/s producing at most 2–3 notification events each. At 10× traffic (5,000 req/s, ~15,000 events/s), a single well-provisioned Redis instance handles this comfortably. Streams with `MAXLEN ~ 100k` bound memory use to predictable levels.

7. **Retry and dead-letter are explicit.** Workers that exhaust retries move the message to a dead-letter stream (a separate stream for manual inspection). Exponential backoff is a consumer-side concern — simple and auditable.

### Negative

1. **No built-in retention policy for stream growth.** Unlike Kafka's time-based retention, Redis Streams cap by length (`MAXLEN`). If a consumer falls behind, it can lose messages before processing them. Mitigation: set `MAXLEN ~ 100k` per stream, monitor consumer lag, and alert when lag approaches the cap. For billing streams, use a higher cap and alert on lag sooner.

2. **Memory-bound, not disk-bound.** All stream data lives in RAM. At our current scale this is negligible (100k stream entries at ~500 bytes each = ~50 MB per stream), but if usage patterns change dramatically, memory costs grow linearly. Kafka spills to disk and is designed for unbounded retention.

3. **No cross-stream ordering guarantees.** Notifications are written to separate streams by type. If an ordering invariant exists between a billing email and a webhook for the same task event, we must embed a correlation ID and enforce ordering on the consumer side. Kafka's single-partition approach would preserve cross-type ordering natively, but we can achieve the same by writing correlated events to the same stream with a shared sequence key.

4. **Exactly-once is consumer-side, not broker-enforced.** The guarantee depends on correct idempotency key implementation. A bug in deduplication logic would produce duplicates. The same risk exists with Kafka's exactly-once semantics when the consumer talks to external systems: Kafka guarantees within-broker exactly-once, but end-to-end requires idempotency on the consumer side regardless.

5. **Smaller ecosystem.** Kafka has connectors (Kafka Connect), schema registry, stream processing (KSQL/KS), and rich monitoring (Burrow, Cruise Control). Redis Streams has no equivalent. We trade ecosystem breadth for operational simplicity, which is the right call for a 6-person team.

---

## Alternatives Considered

### Apache Kafka (Rejected)

**Why it was considered:** Kafka sets the industry standard for message queuing. It offers exactly-once semantics (via transactions), configurable time-based retention, massive throughput (millions of msgs/s), and a mature consumer group protocol that is the conceptual model Streams emulates.

**Why it was rejected:**

- **Operational burden is disproportionate to our scale.** Kafka requires running a cluster of brokers plus a metadata store (KRaft or ZooKeeper). For a team of 6 with no dedicated infra engineer and no Kafka experience, this is a serious operational liability. A misconfigured Kafka cluster degrades in complex, hard-to-diagnose ways: leader rebalance storms, unclean leader elections, log compaction failures, consumer group rebalancing thrash. Redis Streams on existing infrastructure has none of these failure modes.

- **Time to value exceeds the constraint.** Standing up a production Kafka cluster — sizing brokers, configuring replication, setting up monitoring and alerting, learning the client APIs, writing integration tests — conservatively takes 2–3 weeks *before* we write any application code. Redis Streams can be in production with a working consumer in week one.

- **Budget tension.** Self-hosted Kafka demands 3+ brokers for a resilient cluster, plus ZooKeeper/KRaft nodes. On AWS, that's 3–6 EC2 instances with EBS volumes sized for retention. Managed Kafka (MSK, Confluent Cloud) costs more — the entry-level Confluent Cloud cluster alone exceeds our infrastructure budget before we add any compute for consumers.

- **Exactly-once is not a differentiator here.** Kafka's transactional API guarantees exactly-once *within the Kafka cluster* (producer → broker → consumer). End-to-end exactly-once with an external API (SendGrid, a customer's webhook endpoint) still requires idempotency keys on the consumer side, exactly as Redis Streams does. The advantage Kafka claims in this area does not apply to our problem.

- **Overkill for the throughput profile.** Kafka shines at 100K+ msgs/s with replay, long retention, and stream reprocessing. Our peak is ~1,500 events/s. We would pay the full complexity tax for a fraction of Kafka's capacity.

**Migrate path if needed:** Should Redis Streams become a bottleneck at 50–100× current traffic (rather than the 10× target), migrating to Kafka is straightforward: the stream abstraction is similar enough that consumer code adapts with bounded effort, and the producer can dual-write during a cut-over window.

### Amazon Simple Queue Service (SQS) — Not formally evaluated

SQS was mentioned during initial discussion but scoped out because:
- No consumer group model — each queue message is consumed once per visibility timeout, but there is no equivalent to offset tracking or PEL replay.
- No ordering guarantees at scale unless you use FIFO queues, which limit throughput to 300 TPS.
- Adds an AWS dependency with vendor lock-in for the messaging layer.

If Redis Streams proves unsuitable, a re-evaluation would also include SQS + SNS as a serverless alternative.

---

## Migration Plan (Summary)

| Phase | Timeline | Deliverable |
|-------|----------|-------------|
| 1. Core stream infrastructure | Week 1 | Stream creation, producer shim in Flask handlers, worker scaffold |
| 2. Email queue | Week 1–2 | Email consumer, PEL retry, dead-letter stream |
| 3. Webhook queue | Week 2–3 | Webhook consumer, rate limiting per target, retry |
| 4. Billing exactly-once | Week 3–4 | Idempotency key store, billing consumer with dedup |
| 5. Monitoring & cut-over | Week 4 | Lag alerts, dashboards, gradual traffic shift |
| 6. WebSocket push | Q2 | Pub/Sub channels on existing consumer worker pool |

Phases 1–2 alone solve the timeout and cascading-failure problems and fit within the two-week constraint.
