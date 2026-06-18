# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

---

## Context

The Notifier subsystem runs synchronously inside the Flask HTTP request cycle, sending emails and webhooks for task updates, assignments, and completions. At 500 req/s peak with ~2M tasks/month, this coupling has produced four failure modes:

1. **Request timeouts** — average 800ms latency, spikes to 8s during peak hours.
2. **Silent failures** — downstream email or webhook failures drop notifications with no retry or dead-letter queue.
3. **Cascading failures** — two incidents where a slow webhook endpoint exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees** — billing-critical notifications (trial expired, payment failed) have no at-least-once or exactly-once semantics.

### Requirements

- Decouple notification dispatch from the HTTP request cycle.
- Support retry with exponential backoff.
- At-least-once delivery for all notifications; exactly-once for billing events.
- Real-time WebSocket push capability within 2 quarters.
- Handle 10× current traffic (~5,000 req/s peak) without re-architecting.

### Constraints

- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already runs in production (session storage, rate limiting).
- No team experience with Kafka.
- Must deliver value within 2 weeks of setup/migration work.
- Modest budget — cannot afford managed Confluent Cloud at full scale.
- Billing notifications require exactly-once semantics.

---

## Decision

**We will use Redis Streams.**

Redis Streams provides the core messaging primitives we need (consumer groups, at-least-once delivery, stream trimming, range queries) on infrastructure we already operate. It satisfies every hard requirement within the 2-week timeline and avoids introducing a new stateful system that would consume a third of our engineering team's operational capacity.

For billing notifications requiring exactly-once semantics, we pair Redis Streams (at-least-once delivery) with idempotent consumers that deduplicate against a `notification_delivery` table in PostgreSQL. This is the same strategy we would need with Kafka — neither system provides true exactly-once delivery to external systems (email providers, webhook endpoints) without application-level deduplication.

---

## Consequences

### Advantages

- **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. Adding Streams is a configuration change, not a new deployment. Estimated time to first notification flowing through the stream: 1 day.
- **Familiar operational model.** The team already handles Redis performance, memory, and failover. No new debugging skills to acquire under production pressure.
- **Fits current scale comfortably.** Redis can sustain 100k+ writes/second on modest hardware. Our 500 req/s peak (5,000 at 10× growth) is well within range. A single `c6g.large` Redis instance handles this throughput with headroom.
- **Natural WebSocket path.** Redis Pub/Sub pairs directly with Streams for real-time push. We can build a lightweight WebSocket relay using the same Redis connection pool within the 2-quarter window.
- **Stream trimming controls memory.** `XTRIM` with `MAXLEN` keeps the stream bounded. At 5,000 events/s, a capped stream of 1M entries (~3 minutes backlog) uses ~200 MB — negligible against a typical Redis instance.
- **Consumer groups provide at-least-once delivery.** Each consumer gets a unique ID in the group. Acknowledged messages are tracked; unacknowledged ones are redelivered on consumer failure. `XPENDING` + `XCLAIM` gives us the retry machinery.

### Disadvantages

- **No true exactly-once in the stream layer.** Redis Streams guarantee at-least-once delivery at the infrastructure level. Exactly-once for billing requires an idempotency layer in the consumer (dedup key stored in PostgreSQL, checked before dispatch). This is identical to what Kafka would require for external-system delivery.
- **Memory-bound backlog.** Streams live entirely in RAM. If consumers fall behind for minutes (e.g., email provider outage), the backlog must fit in memory. Mitigation: aggressive `MAXLEN` trimming, and a secondary persistence strategy (e.g., writing raw events to S3/PostgreSQL for replay when consumers catch up).
- **No native partitioning.** A single Redis node handles all stream shards. To scale horizontally, you must manually shard by consumer group or use Redis Cluster (which adds operational complexity). At 5,000 req/s peak, a single instance handles the load; above ~20,000 req/s you need to re-architect.
- **No dead-letter queue primitive.** We must build DLT logic ourselves: use `XACK` only after successful delivery; track failed deliveries in a separate Redis stream or PostgreSQL; implement TTL-based escalation.
- **No schema registry.** Producers and consumers must agree on message format by convention. Mitigation: use a shared Python dataclass/Protobuf library checked into the monorepo.

---

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka was rejected for this project at this time. Here is a detailed accounting.

**Why Kafka would be strong here:**

- **Log-based persistence.** Kafka writes to disk. A consumer that falls behind for hours does not risk data loss — storage is independent of memory. This eliminates the memory-bound backlog risk of Redis Streams.
- **Native partitioning.** Topics split across partitions with configurable replication. Linear scalability: add partitions to scale throughput, add brokers for fault tolerance. Handles 100k+ messages/s on modest clusters.
- **Exactly-once semantics (within Kafka).** The Kafka transactional API (`producer.initTransactions()`, `consumer.commitTransaction()`) provides exactly-once delivery *within the Kafka ecosystem*. This is the strongest infrastructure-level guarantee available.
- **Built-in dead-letter queues.** Kafka's DLT pattern (route poison-pill messages to a separate topic) is well-documented and widely practiced.
- **Long message retention.** Configure retention by time (e.g., 7 days) or size. Enables replay, reprocessing, and debugging without S3 fallback.

**Why Kafka was rejected:**

- **Team expertise gap.** Zero team experience with Kafka. The learning curve — broker configuration, partition strategy, consumer group rebalancing, monitoring (JMX metrics, ISR status, lag) — is steep. The team would be learning Kafka under production pressure.
- **Operational tax.** A production Kafka cluster requires at least 3 brokers for fault tolerance, plus ZooKeeper (or KRaft). This is a new stateful system requiring dedicated monitoring, backup, and upgrade procedures. For a 6-person team with no dedicated infrastructure engineer, this overhead is disproportionate to the problem.
- **2-week timeline is unrealistic.** Installing and configuring a 3-broker cluster + ZooKeeper, integrating the Python client, implementing consumer groups, and proving the happy path takes 3–5 days for an experienced team. For a team learning Kafka from scratch: 2–3 weeks minimum — eating the entire delivery window before any business value is delivered.
- **Cost.** Self-hosted Kafka on 3 × `m6g.large` instances costs ~$250/month in compute, plus EBS storage. While not prohibitive, it is non-zero new infrastructure spend. Managed Amazon MSK starts at ~$700/month for a minimal 3-broker cluster. Confluent Cloud would be $1,000+/month — explicitly out of budget.
- **Overkill for current scale.** Kafka excels at 100k+ messages/s, multi-team event sourcing, and streaming data pipelines. Our notification workload at 500–5,000 events/s is a queuing problem, not a stream-processing problem. The architectural complexity buys us capability we will not use for 12–18 months.
- **WebSocket gap.** Kafka does not natively support WebSocket push. We would need an additional bridge service (e.g., Kafka → WebSocket relay) — more infrastructure.

**When Kafka would be the right choice.** If the notification subsystem were handling 20,000+ events/s, or if the event stream were consumed by multiple independent services (not just notification dispatch), Kafka's partitioning and replay capabilities would justify its operational cost. At that stage, the team should have (a) grown to 12+ engineers with at least one infrastructure specialist, and (b) adopted an event-driven architecture across multiple domains. We are not there yet.

---

## Implementation Plan (Summary)

| Phase | Timeline | Deliverable |
|-------|----------|-------------|
| **Phase 1: Stream producer** | Week 1 | Flask middleware intercepts notification events → writes JSON to Redis Stream (`notifier:events`). Response returns immediately after stream write. |
| **Phase 2: Consumer with retry** | Week 2 | Python consumer process reads from consumer group, dispatches email/webhook, XACKs on success. Dead-letter after 3 retries (stored in PostgreSQL `dead_letter_queue` table). |
| **Phase 3: Billing exactly-once** | Week 3 | Idempotency key on `notification_delivery` (event_id + notification_type). Consumer checks delivery table before dispatching. Unique constraint prevents duplicate sends. |
| **Phase 4: WebSocket push** | Q2 | Redis Pub/Sub bridge to WebSocket connections. Same stream, parallel consumer group for real-time push. |

---

## References

- `system_context.md` — full problem statement, metrics, and constraints.
- Redis Streams documentation: https://redis.io/docs/data-types/streams/
- Kafka exactly-once semantics: https://kafka.apache.org/documentation/#semantics
