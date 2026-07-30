# ADR-001: Notification Subsystem — Async Processing Architecture

**Status:** Proposed

---

## Context

The notifications module (email + webhooks for task updates, assignments, completions) runs synchronously inside the HTTP request cycle of our Python/Flask monolith. As the platform has grown to 85k MAU and ~2M tasks/month, this coupling causes three classes of incident:

- **Request timeouts** — average notification latency of 800ms spikes to 8s during peak hours, degrading the entire API.
- **Silent failures** — a downed email provider or webhook endpoint drops the notification permanently. No retry, no dead-letter queue.
- **Cascading failures** — two incidents this year where a single slow webhook caused connection-pool exhaustion across unrelated features.

### Constraints that bound the decision

| Constraint | Impact |
|---|---|
| **Team of 6** (3 senior, 3 mid) with no dedicated infra engineer | Must limit operational surface area. Kafka's ZooKeeper/KRaft, topic tuning, partition rebalancing, and monitoring burden land on the same six people who ship features. |
| **No Kafka experience on the team** | Learning curve + production blind spots (offset management, unclean leader elections, consumer lag) create a window of elevated risk. |
| **Already running Redis** for session storage and rate limiting | Adding a stream-based consumer to the existing Redis cluster adds zero new infrastructure, zero new credentials, zero new backup procedures. |
| **Must deliver value within 2 weeks** | Redis Streams integration (producer-side `XADD`, consumer-side `XREADGROUP`) can ship next sprint. Kafka with provisioning, schema registry, and client tuning cannot. |
| **Modest budget, no managed Confluent** | Self-hosted Kafka on EC2 or EBS costs ~$200-600/month for a 3-broker baseline before team time. Redis Streams adds ~$20/month for increased memory on the existing node. |
| **Exactly-once semantics for billing notifications** | For push delivery to external systems (email, webhook), true distributed exactly-once is impossible regardless of transport — the external system has no transaction coordinator. The practical solution (at-least-once + idempotent consumer + dedup key) applies identically to both Kafka and Redis Streams. Kafka's transactions buy nothing here because the sink is outside the transaction boundary. |

### Scaling target

10× current traffic (peak ~5,000 req/s), real-time WebSocket push within two quarters, and exactly-once guarantees for billing-critical events.

---

## Decision

**Use Redis Streams** with at-least-once delivery semantics and an idempotent consumer backed by PostgreSQL deduplication.

We deploy notifications as a background worker process that reads from a Redis Stream via consumer groups (`XREADGROUP`). The Flask monolith writes notification events to the stream with `XADD`. Workers process each event — sending emails via SES/SendGrid and webhooks to configured URLs — then acknowledge with `XACK`. Failed events re-enter the PEL (Pending Entry List) for retry with exponential backoff. Events that exhaust their retry budget move to a Redis-backed dead-letter queue (a second stream).

Billing-critical notifications (trial expiry, payment failure, plan downgrade) carry a unique `idempotency_key` (UUID). The consumer checks this key against a PostgreSQL `notification_deliveries` table with a unique constraint before processing, guaranteeing at-most-once processing per event — which, combined with the stream's at-least-once delivery, yields **effectively-once semantics** for billing events without requiring Kafka's transaction protocol.

WebSocket push (planned within two quarters) will be served by a thin subscription layer that reads from a dedicated stream keyed by user ID, bridged via Redis Pub/Sub or by the worker itself.

Justification is structured along four axes:

### 1. Operational fit (the decisive constraint)

A 6-person team has no surplus capacity to learn, tune, and babysit a Kafka cluster. Redis Streams reuses infrastructure the team already operates and understands. The entire notification pipeline can be implemented in a single `worker.py` process using the `redis-py` library already in the dependency tree. No new port to open, no new IAM policy, no new backup strategy.

### 2. Scale adequacy

Current peak is 500 req/s. Even at 10× (5,000 req/s), assuming ~3 notification events per request, that is 15,000 writes/s. A modest Redis instance (c6g.large, 2 vCPU, 4 GiB RAM) handles 100k+ operations/s on `XADD`. Streams are not the bottleneck at this scale. The memory footprint at 15k events/s with a capped stream (`MAXLEN ~100000`) stays under 1 GB for typical notification payloads (~1 KB each). Kafka's throughput advantage (millions of msg/s) is irrelevant here — Redis Streams are already over-provisioned for 10× growth.

### 3. Exactly-once is a transport-independent problem

Kafka's exactly-once semantics (EOS) coordinate producers, brokers, and consumers within the Kafka ecosystem via transactions. This works when producer and consumer are both Kafka-aware and the sink is Kafka itself. Our sink is external HTTP endpoints (email providers, webhook URLs). Kafka's EOS has no jurisdiction there.

The pattern for exactly-once delivery to an external system is identical on both transports:

1. **At-least-once** delivery to the consumer (guaranteed by consumer groups + offset/ID tracking)
2. **Idempotent processing** via a dedup check (PostgreSQL unique constraint on `notification_id`)
3. **Atomic acknowledgement** — commit the dedup row and acknowledge the stream message in the same database transaction (or handle carefully to avoid the double-ack gap)

Redis Streams handles step 1 via PEL. Step 2 and 3 are identical on both platforms. Redis Streams loses nothing on exactly-once for this use case.

### 4. WebSocket push natural fit

Adding real-time push requires fanning notifications to per-user channels. Redis Pub/Sub (already available in the same instance) is a standard pattern for this: the stream consumer publishes to a user-specific Pub/Sub channel, and WebSocket servers subscribe. This keeps the notification pipeline unified — no second queue system needed.

---

## Consequences

### Positive

- **0 new infrastructure** — uses the existing Redis cluster. Setup time: hours, not weeks.
- **Fastest path to value** — the first notification events can flow async within a single sprint. The monolith only needs `XADD` calls; the worker only needs `XREADGROUP`.
- **Familiar tooling** — every engineer on the team has used Redis. No Kafka literature-review phase required.
- **Bounded operational cost** — a c6g.large upgrade covers the notification load at current + 10× scale for ~$20/month. No dedicated broker cluster, no ZooKeeper nodes.
- **Unified real-time push** — Redis Pub/Sub bridges notification events to WebSocket subscribers on the same instance without a second technology.
- **Graceful degradation** — if Redis is down, `XADD` fails fast, the monolith returns a 503 or falls back to a PostgreSQL queue table (already has a connection pool). Compare to Kafka: a `send()` timeout blocks or requires its own circuit breaker.

### Negative

- **Memory-bound retention** — Redis Streams live in RAM. Capped streams (`MAXLEN`) are essential. Unlike Kafka's log (disk-backed, configurable retention by time/size), you cannot keep months of notification history in Redis without high memory costs. Mitigation: archive processed events to PostgreSQL or S3 for audit/replay. This is a reasonable trade-off — notification history is query-pattern different from streaming (users search old notifications by date, project, user), so it belongs in PostgreSQL anyway.
- **No automatic consumer rebalancing** — when adding or removing worker instances, newly idle partitions are not automatically redistributed. Mitigation: with a 6-person team and modest event volume, this can run with a simple coordinator (Redis key lease) or a static partition-per-worker assignment. The 10× scale target (5k req/s, ~15k events/s) does not require elastic auto-scaling of workers — a fixed pool of 3-5 workers handles it.
- **No built-in dead-letter queue** — Redis Streams have no "poison pill" concept. Mitigation: straightforward to implement — a second stream (`notifications:dlq`) with a retry-count header. The consumer `XACK`s from the main stream on retry exhaustion and `XADD`s to the DLQ. Kafka also requires custom DLQ infrastructure on the consumer side.
- **Persistence gap** — Redis's default RDB snapshots can lose up to a configured time window of data on crash. AOF with `appendfsync everysec` loses at most 1 second. Mitigation: for billing-critical notifications, dual-write to PostgreSQL before `XADD`, and the consumer checks PostgreSQL for the canonical event. This is the same belt-and-suspenders approach you'd take with Kafka against a broker crash anyway.
- **Smaller community around streaming patterns** — Kafka has richer ecosystem (Kafka Connect, ksqlDB, stream processing libraries). Mitigation: our use case is queue + retry + dead letter — the simplest streaming pattern. We don't need stream-table joins or exactly-once sinks. The `redis-py` and `rq`/`dramatiq` ecosystems cover this.

---

## Alternatives Considered

### Apache Kafka

Rejected for several reasons that compound each other:

**Operational complexity.** A production Kafka deployment minimally requires a 3-broker cluster (or 3 KRaft nodes). This means provisioning, securing, monitoring, and tuning three VMs worth of JVM processes. The team has no Kafka expertise — every broker restart, partition leader election, or consumer group rebalance becomes a learning event with production risk. For a 6-person feature team shipping a SaaS product, Kafka's operational load is disproportionate to the notification problem being solved.

**Setup timeline incompatible with the 2-week constraint.** A functional Redis Streams pipeline can be written, tested, and deployed by two engineers in a single sprint. Kafka requires broker provisioning (even on managed MSK, which is out of budget), schema registry setup, topic configuration, client library evaluation (`confluent-kafka-python` vs `kafka-python`), and production tuning (acks, min.insync.replicas, compression, batch size). Two weeks is aggressive for a team learning Kafka from scratch.

**Throughput overprovisioning.** Kafka's design point is millions of messages per second across dozens of partitions. Our peak is 500 req/s. At 10× it is 5,000 req/s. Redis Streams handle this with headroom to spare. Paying Kafka's operational cost for throughput we will never use is engineering waste.

**Exactly-once advantage is illusory for this use case.** As argued above, Kafka's transactions coordinate within Kafka but do not extend to external HTTP endpoints. Both Kafka and Redis Streams require the same idempotent consumer pattern for real exactly-once semantics with external sinks. Kafka's EOS does not simplify the billing-notification requirement.

**WebSocket push requires a second system anyway.** Kafka does not have a native pub/sub bridging to WebSocket connections. We would need to run a separate bridge consumer that translates Kafka messages into WebSocket pushes — plus the Kafka cluster itself. Redis Streams + Pub/Sub unifies this on one instance.

**Self-hosted Kafka costs are not trivial.** A 3-broker cluster on m6g.large (2 vCPU, 8 GiB) costs ~$500/month in EC2 + EBS provisioned IOPS. Managed alternatives (Confluent Cloud, AWS MSK) start at ~$100-200/month but the team has explicitly stated the budget cannot support managed Confluent at full scale. Redis Streams adds ~$20/month to the existing Redis bill.

**In Kafka's favor:** If the company's long-term architecture includes event sourcing, CQRS, or a central event bus spanning multiple services (notifications, audit logs, analytics, search indexing), Kafka becomes the right foundation. For *just* a notification queue today, it is premature and costly.
