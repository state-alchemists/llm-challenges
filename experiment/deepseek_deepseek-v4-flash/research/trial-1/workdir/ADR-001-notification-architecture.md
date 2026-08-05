# ADR-001: Notification Architecture — Asynchronous Notifications with Redis Streams

## Status

Proposed — 2026-08-05

## Context

The notifier module sends emails and webhooks when tasks are updated, assigned, or completed. Today it runs synchronously inside the Flask request cycle, and that coupling is the root cause of four production symptoms:

1. **Request timeouts** — notification work blocks the HTTP response; average latency is 800 ms with spikes to 8 s at peak.
2. **Silent failures** — when an email provider or webhook endpoint is down, the notification is dropped with no retry and no dead-letter queue.
3. **Cascading failures** — two incidents this year where a slow webhook exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") must not be lost, but nothing today guarantees delivery, let alone exactly-once.

Relevant facts about the platform:

- **Scale**: 85,000 monthly active users, ~2M tasks created/month, ~500 req/s peak during business hours.
- **Stack**: Python/Flask monolith (~50k LOC), PostgreSQL (single primary + one read replica), 4 web servers behind nginx on AWS, Redis in production for session storage and rate limiting.
- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer, no Kafka experience.

Targets for the notification subsystem:

- Decouple notifications from the HTTP request cycle (async processing).
- Retry with exponential backoff.
- At-least-once delivery for billing events; exactly-once where feasible.
- Real-time WebSocket push notifications within 2 quarters.
- 10x traffic growth without re-architecting.

Constraints:

- Must deliver value within 2 weeks of setup/migration.
- Modest budget — cannot afford managed Confluent Cloud at full scale today.
- Must maintain exactly-once semantics for billing notifications.

## Decision

**Adopt Redis Streams as the notification message bus, running on the existing Redis infrastructure.** This meets every functional requirement at current and 10x scale while adding zero new operational surface to a 6-person team.

Concretely:

1. **Producers** — the Flask monolith stops sending emails/webhooks inline. On task/billing events it appends a JSON message to a stream with `XADD` (e.g., one stream per category: `notif:task`, `notif:billing`, `notif:webhook`). Producer work is a single Redis operation; the HTTP request no longer waits on providers.
2. **Consumers** — background worker processes (separate from the web tier) read with `XREADGROUP` from dedicated consumer groups, one per stream. Workers perform the side effects: email via the provider API, webhook POST, and (within 2 quarters) fan-out to a WebSocket push publisher.
3. **At-least-once delivery** — consumer groups track unacknowledged messages in the pending entries list (PEL); a worker must `XACK` after the side effect completes. Crash recovery: unacked messages are re-claimed via `XAUTOCLAIM` (Redis 6.2+) after a visibility window, so a dead worker does not lose events.
4. **Retry with exponential backoff** — on failure, leave the message unacked with a growing idle threshold (the backoff delay), so `XAUTOCLAIM` redelivers after the wait; after N attempts, `XACK` the original and write it to a dead-letter stream (`notif:dlq`) that alerts on insert.
5. **Exactly-once for billing** — at-least-once from the bus + idempotent consumers = effectively exactly-once. Every event carries a unique `event_id`; consumers deduplicate before the side effect with `SET NX` + TTL in Redis (or a unique constraint in PostgreSQL), and webhook payloads / provider API calls include `event_id` as an idempotency key. This is the only way to get end-to-end exactly-once against *external* systems; the broker choice cannot provide it (see Alternatives Considered).
6. **Ordering** — streams preserve insertion order, and a consumer group delivers in order while concurrency per stream is 1. Where per-entity ordering matters (e.g., all billing events for one customer), write entity-keyed streams or consume one stream with a single worker; cross-entity ordering is not a product requirement.
7. **Isolation** — notification streams get their own Redis logical DB (or a small second Redis node if memory pressure appears) so stream churn cannot degrade session/rate-limit latency. Streams are trimmed with `MAXLEN`; PEL depth and memory are monitored.
8. **Future-proofing** — producers and consumers talk to a thin `NotifierBus` interface, so the broker can be swapped later (e.g., to Kafka) without rewriting the application.

**Why Redis Streams wins here:** the workload is small — ~2M tasks/month is roughly 10 notification events/sec on average and low hundreds/sec at peak, and even a generous 10x bound stays in the low thousands/sec. Redis handles tens of thousands of stream operations/sec per node, so we have 1–2 orders of magnitude of headroom at 10x, and the team already runs and operates Redis. Kafka's advantages (millions of msg/s, disk-based retention, automatic partitioning) are capacity and scale features this workload does not consume; we would pay for them with a new distributed system to learn and operate inside a 2-week delivery window.

## Consequences

### Positive

- **Reuses production-tested infrastructure.** Redis is already deployed for sessions/rate limiting; streams are a data structure in the same service. Setup is days, not weeks, satisfying the 2-week constraint.
- **Fits the team.** Six engineers, no infra specialist, no Kafka experience: streams have a small API surface (`XADD` / `XREADGROUP` / `XACK`), are supported by `redis-py`, and the operational failure modes (memory, PEL growth) are ones the team can already reason about.
- **At-least-once for everything, effectively exactly-once for billing**, via consumer-group acks plus event-ID dedup.
- **Throughput headroom for 10x growth** without re-architecting; current event rates are roughly three orders of magnitude below the broker's ceiling.
- **Retry, backoff, and DLQ are first-class patterns** built from existing primitives (PEL, `XAUTOCLAIM`, a `notif:dlq` stream), not add-on infrastructure.
- **WebSocket push fits** — the same streams feed a push consumer group within 2 quarters; no new broker required.
- **Cost.** No new managed service, no new EC2 fleet, no Confluent license; the modest budget is respected.
- **Reversible.** The `NotifierBus` interface keeps Kafka available as a future option if scale or retention requirements fundamentally change.

### Negative

- **Memory-bound retention.** Streams live in RAM; long retention is expensive and bloats RDB snapshots/AOF. We must trim aggressively (`MAXLEN`) and treat the bus as short-lived — PostgreSQL remains the record of record for audit history. Kafka's disk-based retention is better for long replay, which notifications do not need.
- **No automatic partitioning.** Scaling consumers horizontally means manually sharding across multiple streams (keyed hashing); Kafka auto-balances partitions. Manageable at 10x but requires keying discipline from day one.
- **Ordering is per-stream, not global.** Multiple consumers on one stream deliver round-robin; cross-stream ordering needs deliberate key design. Kafka has the same per-partition limitation but makes the trade-off more explicit.
- **Redis is a single node** unless managed HA is used (e.g., ElastiCache with replication). A Redis outage pauses notification processing; mitigated by existing managed hosting, monitoring, and the fact that unacked events survive in the PEL for redelivery.
- **No native exactly-once.** The dedup burden lives in the consumers. This is not a regression — Kafka's exactly-once also stops at the broker boundary for external side effects (see Alternatives Considered).
- **Smaller ecosystem** than Kafka (no Connect, no Schema Registry). The team writes its own consumers — acceptable, since this is a Python application and `redis-py` is already a dependency.

## Alternatives Considered

### Apache Kafka — rejected

- **Operational complexity is the decisive factor.** A well-run Kafka deployment is a distributed system of its own: brokers, partition sizing, ISR/rebalance monitoring, retention tuning, disk management. With 6 people, no infrastructure engineer, no Kafka experience, and a 2-week delivery window, self-hosting Kafka while also building the notification workers is not credible. Managed Confluent Cloud removes the ops burden but exceeds the stated budget at full scale. Redis Streams adds zero new moving parts.
- **Throughput is the wrong axis.** Kafka's strength is hundreds of thousands to millions of messages/sec with long disk-based retention and replay. Our workload is ~10 events/sec today and low thousands/sec at 10x — roughly three orders of magnitude below Kafka's design point. Choosing Kafka buys capacity we will not use and pays for it in complexity.
- **Exactly-once semantics do not deliver the requirement.** Kafka's exactly-once (idempotent producer + transactions) guarantees exactly-once *within the Kafka pipeline* — read-process-write between topics. It does not guarantee exactly-once delivery to an email provider or a webhook, which are external systems outside the transaction. Billing exactly-once still requires the same consumer-side idempotency/dedup design we implement on Redis Streams, so Kafka does not close the gap that motivated the requirement.
- **Ordering parity.** Kafka offers per-partition ordering, directly analogous to per-stream ordering in Redis; both require keying discipline for entity-level guarantees. No advantage at this workload.
- **Retention mismatch.** Disk-based retention and replay are genuinely better in Kafka, but notifications are ephemeral by nature; long-lived audit data belongs in PostgreSQL, which we already run.

Kafka remains the fallback trigger for a future migration: sustained rates in the tens of thousands of events/sec, a hard requirement for multi-day replay or analytics over the event stream, or a need for the Connect/Schema Registry ecosystem. The `NotifierBus` interface is the escape hatch for that day.

*Scope note: this ADR evaluates the two requested options. Other brokers (RabbitMQ, SQS) would fail on the same primary criterion as Kafka — introducing a new system to operate when the existing Redis infrastructure covers the requirement.*
