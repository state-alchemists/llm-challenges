# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

## Context

Our SaaS project management platform handles ~2M tasks/month across 85,000 MAUs, peaking at ~500 req/s. The notifications module (emails, webhooks for task updates/assignments/completions) runs synchronously inside the HTTP request cycle — a design that no longer scales. We are seeing:

- **Request timeouts**: Average notification latency 800ms, spiking to 8s during peak hours.
- **Silent failures**: Downstream email or webhook failures drop notifications with no retry or dead-letter queue.
- **Cascading failures**: Two incidents where a slow webhook caused PostgreSQL connection pool exhaustion, taking down unrelated features.
- **No delivery guarantees**: Billing-critical events (trial expiry, payment failure) need exactly-once delivery; today they get best-effort at best.

We must decouple notification dispatch from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery with exactly-once for billing events, support upcoming WebSocket push, and handle 10× traffic growth (~5,000 req/s, ~10,000 notifications/s) without re-architecting.

**Team constraints**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer, modest AWS budget, no prior Kafka experience. Redis is already in production for session storage and rate limiting. We have a hard two-week window to deliver initial value.

## Decision

**Use Redis Streams as the notification backbone.**

We will add a Redis Stream per notification category (email, webhook, billing) and introduce lightweight worker processes that consume from these streams via `XREADGROUP` with pending-entry tracking and `XCLAIM` for retry. Billing events will carry a producer-generated immutable event ID, with consumer-side idempotency deduplication against a Redis Set (short TTL) backed by a PostgreSQL unique constraint for durability.

## Consequences

### Benefits

- **Fastest path to value.** Redis is already deployed, tuned, and understood by the team. Adding a stream requires only `XADD` in the request handler and a consumer worker using `XREADGROUP`. Initial production value within days, not weeks. Fits comfortably under the two-week window.

- **Lowest operational burden for a 6-person team.** No new infrastructure to provision, no new stateful service to monitor, no new failure modes to learn. The Redis instance already on-call handles streams alongside existing session/rate-limit workloads. Kafka would add a ZooKeeper or KRaft ensemble, broker JVM tuning, partition rebalancing, and a new client library — none of which the team has experience with.

- **Adequate throughput headroom.** 10× growth yields ~10,000 notifications/s peak. A single Redis node handles 100,000+ operations/s for streams. Throughput is not a constraint at this scale. Kafka's million-msg/s throughput is surplus that comes with disproportionate operational cost.

- **Natural fit for WebSocket push.** Redis Pub/Sub — already in the same ecosystem — can bridge stream events to WebSocket connections with minimal glue code. Bridging Kafka to WebSockets requires Kafka Connect, a dedicated bridge service, or a second message broker, adding complexity well beyond the 6-person team's reach in two quarters.

- **Consumer groups and retry are first-class.** `XREADGROUP` provides exactly the fan-out pattern notification workers need. `XPENDING` lists unacknowledged messages; `XCLAIM` transfers them to another consumer for retry. Exponential backoff is trivially implemented by the consumer re-enqueuing to a delayed stream or sleeping before `XCLAIM`. No external retry infrastructure needed.

- **Billing exactly-once is achievable.** Redis Streams (like Kafka) provides at-least-once delivery natively, not end-to-end exactly-once. But exactly-once is a consumer-side property. Our approach: each billing event carries a unique producer-generated ID (`billing_<user_id>_<timestamp>_<uuid>`); the consumer checks a Redis Set (TTL 7 days) and the billing PostgreSQL table (unique constraint on `event_id`) before processing. This gives exactly-once semantics for billing without requiring broker-level transactions.

- **Familiar debugging and monitoring.** The team already knows `redis-cli`, `MONITOR`, `SLOWLOG`, and memory-metric dashboards. Kafka debugging — inspecting consumer lag, partition leadership changes, unclean leader elections — would require ramping up on entirely new tooling and concepts.

### Trade-offs / Risks

- **Memory-bound retention.** Redis stores stream data in memory. If a consumer falls far behind — or if we need weeks-long replay — we either evict old entries (via `MAXLEN ~ <count>`) or provision more memory. For notifications, this is acceptable: the window for retry is hours, not weeks. Billing events are durably stored in PostgreSQL. If long-term event sourcing becomes a requirement in the future, Kafka or a dedicated log store would be needed.

- **No native partition scaling.** Redis Streams scale vertically (bigger instance) rather than horizontally (more partitions). At 10× growth (~10,000 msg/s) a single Redis node suffices. Beyond ~100,000 msg/s or when the node's memory footprint exceeds feasible instance sizes, we would need to shard across multiple Redis instances (e.g., by notification category or user hash). This is more engineering work than adding Kafka partitions, but it's a future concern, not an immediate constraint.

- **No broker-level exactly-once semantics.** Kafka's idempotent producer and transactional API can prevent duplicates within the Kafka ecosystem. Redis Streams cannot. The consumer-side dedup approach described above is battle-tested but requires discipline: the consumer must make the dedup check and the side-effect (sending the email, writing the PG row) *idempotent or transactional*. We mitigate this by using PG's unique constraint as the final authority for billing events — a double-check that survives a consumer crash between dedup-set insertion and side-effect completion.

- **Persistence model is eventually consistent by default.** Redis Append-Only File (AOF) persistence provides durability, but a failure between `XADD` returning success and the AOF sync losing the write is possible (though rare with `appendfsync always` at a performance cost). For billing events, the producer should also write to PostgreSQL before enqueuing, so no notification is ever invented — worst case, a billing event is produced twice and deduplicated downstream.

- **Smaller community and library ecosystem for streams.** Kafka has richer tooling for stream processing (Kafka Streams, ksqlDB), schema management (Schema Registry), and connectors. For our use case — a notification worker that reads, sends, and acknowledges — we don't need stream processing. The Python `redis` library's stream support is mature and well-documented.

## Alternatives Considered

### Apache Kafka (rejected)

Kafka is an excellent distributed log, and many organizations run notification systems on it successfully. It was rejected here for three reasons that together are disqualifying:

**Operational cost overwhelms team capacity.** Kafka is a distributed system that demands distributed-system operations. A minimal production cluster requires at least 3 brokers (ideally 5 for rack-aware replication), plus ZooKeeper or a KRaft controller quorum. Each broker needs careful JVM heap tuning, disk sizing (Kafka is I/O-bound, not memory-bound), partition-count planning, and ongoing monitoring for consumer lag, unclean leader elections, under-replicated partitions, and disk throughput. A 6-person team with no infra engineer and no Kafka experience would be incurring significant operational debt from day one — before a single notification is delivered. The self-hosted budget constraint rules out Confluent Cloud, which would offload some of this burden.

**Setup timeline conflicts with the two-week constraint.** Standing up Kafka, tuning it for production, writing producers and consumers in a new client library (`confluent-kafka-python` or `kafka-python`), wiring up monitoring, and training the team on its failure modes cannot be done in two weeks. Redis Streams replaces a synchronous call with `XADD` and a `while True: XREADGROUP` loop in the same Redis library the team already imports.

**Kafka's strengths don't match the problem.** Kafka excels at:
- **Very high throughput** (millions of msg/s) — we need ~10,000 msg/s at 10× growth.
- **Long-term immutable storage** — we need hours-to-days retention for retry, not event sourcing.
- **Stream processing** — we need a worker that sends HTTP/SMTP requests, not a topology of joins, aggregations, and windowed operations.
- **Exactly-once semantics within the ecosystem** — our end-to-end exactly-once still requires consumer-side idempotency regardless of broker choice.

Every Kafka advantage for this problem is also achievable with Redis Streams at a fraction of the operational cost, and the aspects where Kafka clearly wins (scale beyond 100k msg/s, years-long log retention, complex stream processing) do not apply to our notification workload now or at 10× growth.

Kafka would be the right choice if we were building an event-sourced platform, running analytics pipelines over the event stream, or expecting sustained throughput above 100,000 msg/s. None of those are our current or planned requirements.

---

*Decision recorded by the engineering team. To revisit this decision, the trigger conditions would be: sustained notification throughput exceeding 100,000 msg/s, a requirement for >30-day event replay, or the team growing to include dedicated infrastructure engineering capacity.*
