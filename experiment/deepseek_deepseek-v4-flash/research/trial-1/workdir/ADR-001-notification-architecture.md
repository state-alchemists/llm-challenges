# ADR-001: Notification Subsystem — Redis Streams

## Status

Proposed

## Context

The notifications module sends emails and webhooks when tasks are updated, assigned, or completed (system_context.md:20). Today this runs synchronously inside the Flask request cycle (system_context.md:16), causing four production failures (system_context.md:22-25):

1. **Request timeouts** — notification delivery blocks the response; average latency is 800ms with spikes to 8s at peak.
2. **Silent failures** — when an email provider or webhook endpoint is down, the notification is dropped with no retry and no dead-letter queue.
3. **Cascading failures** — two incidents this year where a slow webhook endpoint exhausted the connection pool and took down unrelated features.
4. **No delivery guarantees** — billing-critical events ("trial expired", "payment failed") must be delivered exactly once, but nothing enforces that today.

The target: decouple notification delivery from the HTTP request cycle, retry with exponential backoff, at-least-once delivery for most events with exactly-once where feasible for billing, WebSocket push within two quarters, and 10x traffic growth without re-architecting (system_context.md:29-34).

Constraints (system_context.md:36-43):

- Engineering team of 6 (3 senior, 3 mid-level), **no dedicated infrastructure engineer**.
- Redis already runs in production for session storage and rate limiting.
- No Kafka experience on the team.
- At most two weeks of setup/migration before delivering value.
- Modest budget — managed Confluent Cloud at full scale is unaffordable today.
- Exactly-once semantics required for billing notifications.

Scale reality: ~500 req/s peak and ~2M tasks/month (system_context.md:7-8). Even at 10x growth, peak notification volume is tens of thousands of messages/second — small for either candidate. Scale is not the differentiator; operational fit is.

## Decision

Use **Redis Streams** as the notification message bus.

- **Producer side**: Flask request handlers stop sending synchronously. They write an event with `XADD` into an events stream, returning immediately. To close the crash window between the database commit and the stream write, events are staged in a Postgres transactional outbox and relayed into the stream.
- **Consumers**: a pool of 2–4 worker processes reads with `XREADGROUP` and acknowledges with `XACK` after successful delivery.
- **Delivery semantics**: consumer groups + `XACK` give at-least-once. Unacknowledged entries remain in the Pending Entries List (PEL); entries held by a crashed worker are reclaimed with `XAUTOCLAIM` after an idle timeout and redelivered.
- **Retry and DLQ**: failed deliveries are re-enqueued with a delivery-count field and exponential backoff; after N attempts they move to a `dlq` stream for inspection.
- **Exactly-once for billing**: no message broker provides true end-to-end exactly-once for external side effects — an email send or webhook call cannot be made transactional. Exactly-once is therefore implemented as **at-least-once delivery plus an idempotent consumer**: every event carries a unique event ID, and the consumer deduplicates against a unique constraint in Postgres (or a `SET NX` in Redis) before acting. This is the standard — and the only sound — mechanism for this requirement, regardless of broker.
- **Ordering**: a stream preserves insertion order; a consumer group hands each entry to exactly one consumer, so global order is guaranteed only for a single consumer. Where per-entity order matters (e.g., state transitions for one task), route the entity's events through one consumer or shard per-entity streams. Notification fan-out does not require global ordering; the per-entity guarantee is documented.
- **Retention**: streams have no time-based expiry. They are bounded with `XTRIM` (MAXLEN/MINID) and `XPENDING` is monitored to catch stuck consumers. Notifications are consumed in seconds-to-minutes, so hours of retention are ample.
- **WebSocket push**: the same Redis instance serves the gateway — durable per-user streams for missed events, Pub/Sub for ephemeral broadcast. No new infrastructure.

**Justification**: the deciding properties are operational complexity and time-to-value, not raw throughput. The team already operates Redis in production (system_context.md:39), so there is no new service to provision, secure, monitor, or back up; the migration lands in days, inside the two-week constraint (system_context.md:41), at near-zero marginal cost (system_context.md:42). The 10x target — tens of thousands of messages/second — sits far below Redis Streams' single-node capacity of hundreds of thousands of small messages per second, so the bus is not the bottleneck. Consumer groups deliver the at-least-once semantics, retry, and dead-lettering the problem requires, and idempotent consumers deliver the exactly-once guarantee billing needs.

## Consequences

### Pros

- **Operational simplicity** — no new service, no new expertise: the 6-person team already runs Redis (system_context.md:38-39). Consumer groups are a mature, well-documented feature with client support already in the Python stack.
- **Fast to ship** — days of work, not weeks; the two-week constraint is met with margin.
- **Low cost** — incremental load on existing Redis (at most a modest instance bump) versus standing up a broker cluster.
- **Throughput headroom** — hundreds of thousands of messages/second per node comfortably covers 10x current traffic; the bottleneck shifts to workers, which scale horizontally.
- **Delivery guarantees** — at-least-once, retry with backoff, and dead-lettering are expressed natively with consumer groups, the PEL, `XAUTOCLAIM`, and a DLQ stream; no custom queueing machinery.
- **Exactly-once for billing** — event-ID idempotency delivers the required guarantee with a mechanism that is broker-independent and auditable.
- **WebSocket fit** — the gateway runs on the same Redis, keeping a single operational surface.

### Cons

- **Ordering is weaker than Kafka** — consumer-group delivery to multiple consumers does not guarantee global order. Mitigation: per-entity streams or single-consumer reads where strict order matters; accepted for notification workloads.
- **No time-based retention** — streams grow until trimmed; an explicit `XTRIM` policy and `XPENDING` monitoring are required. Kafka provides time/size retention and compaction out of the box. Mitigation is discipline, not a feature.
- **Durability ceiling** — Redis persistence (RDB/AOF) is not a replicated log. A Redis failure can lose recently written, unacknowledged events. Mitigation: AOF with an aggressive fsync policy, monitoring, and idempotent consumers (duplicates are safe — though loss remains possible in the crash window). Redis is already critical-path for sessions; this elevates its risk profile further.
- **Single-node scale ceiling** — beyond one node, Redis Cluster adds real complexity. The 10x target stays comfortably on one node, but the ceiling is lower than Kafka's.
- **No Kafka ecosystem** — no schema registry, connectors, or Kafka-native tooling. Not needed for this pipeline.

## Alternatives Considered

**Apache Kafka** — rejected.

Kafka's strengths are real: millions of messages/second per broker; a durable, replicated, time/size-retention log with replay; partition-level ordering with keyed partitioning; mature consumer-group rebalancing; and Kafka-to-Kafka exactly-once via transactions (KIP-98).

It is rejected on four grounds:

1. **Operational complexity is disqualifying for this team.** Six people, no infrastructure engineer (system_context.md:38), and zero Kafka experience (system_context.md:40). Self-hosting Kafka — brokers, KRaft controllers, ISR tuning, partition rebalancing, upgrade cycles, monitoring — is a permanent operational tax, not a one-time setup. Managed Kafka (Confluent Cloud/MSK) removes some of that burden but exceeds the modest budget (system_context.md:42) and still requires Kafka-specific expertise to run correctly.
2. **The two-week constraint cannot be met.** Standing up a broker cluster, learning the operational model, and migrating the notification path within two weeks — with a team that has no Kafka experience — is not credible. Redis Streams ships in days.
3. **The scale does not need it.** 10x current traffic is tens of thousands of messages/second, which Redis Streams covers on a single node. Kafka's throughput advantage matters only at a scale this platform will not reach in the planning horizon.
4. **It buys no delivery-guarantee advantage.** Kafka's exactly-once transactions apply only when the sink is Kafka itself. Email and webhook delivery are external side effects, so exactly-once still requires an idempotent consumer — the same mechanism used with Redis Streams. Kafka would add cost and complexity without improving the one guarantee that matters for billing.

**Revisit condition**: adopt Kafka if any of these become true — sustained volume beyond ~100k messages/second, multi-region durability, long-term retention/replay, or many independent consumer groups over the same history. To keep that door open, the queue is hidden behind a narrow interface (enqueue / read / acknowledge) and events carry a stable schema with unique IDs from day one.
