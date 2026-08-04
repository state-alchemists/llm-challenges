# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails and webhooks on task updates, assignments, and completions — synchronously inside the HTTP request cycle. This causes request timeouts (average 800ms, spikes to 8s), silent notification drops with no retry or dead-letter queue, and cascading failures where slow webhook endpoints exhaust the DB connection pool.

We need to decouple notifications from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), and support real-time WebSocket push within two quarters. The system must handle 10x traffic growth without re-architecting.

Constraints: 6-person engineering team (3 senior, 3 mid-level, no dedicated infra), Redis already in production for sessions/rate limiting, no Kafka experience on the team, at most 2 weeks before delivering value, modest budget that cannot sustain managed Confluent Cloud at scale, and exactly-once semantics required for billing notifications.

## Decision

We choose **Redis Streams** as the notification subsystem's message backbone.

Justification follows from the constraints:

1. **Operational fit.** Redis is already in production with team expertise. Adding streams uses existing infrastructure and operational knowledge — no new cluster to provision, monitor, or patch. With no dedicated infra engineer and a 2-week value deadline, standing up a Kafka cluster (even managed) is unrealistic.

2. **Throughput is sufficient.** Redis Streams handle 100k+ messages/s on a single node with `XADD`. Our 10x scaling target (~5,000 msg/s peak, conservatively estimated from 500 req/s × ~10 notification events) sits well within that envelope. Kafka's marginal throughput advantage (millions of msg/s in a cluster) is capacity we don't need and can't justify operating.

3. **Consumer groups.** Redis Streams support consumer groups natively (`XGROUP`, `XREADGROUP`), giving us partitioned, load-balanced consumption with per-consumer pending-entry lists — the core primitive we need for retry and at-least-once delivery. A pending message unacknowledged after a configurable idle timeout (`XPENDING` + `XCLAIM`) becomes available for reclaim, which maps directly to our exponential-backoff retry requirement.

4. **Exactly-once for billing.** Kafka offers exactly-once semantics (idempotent producers + transactional consumers) natively; Redis Streams do not. We close this gap at the application layer: each billing notification carries an idempotency key, and the consumer checks a deduplication table in PostgreSQL before processing. Combined with at-least-once delivery from the stream and a "processed" marker written transactionally alongside business state, this achieves effective exactly-once — the same pattern used by systems like Stripe. This is more work than Kafka's built-in support, but it is confined to a small, well-scoped code path and eliminates the operational cost of running Kafka for one feature.

5. **Message retention.** Redis Streams default to a max-length trim policy (`MAXLEN`) or a time-based TTL, keeping only what's needed. Kafka's unbounded retention is an advantage for event replay and audit, but our use case is fire-and-process — we need delivery guarantees, not a durable event log. For audit, we write notification state to PostgreSQL, which is our source of truth.

6. **Time to value.** With Redis Streams, a senior engineer can ship a working async notification pipeline in under two weeks using the existing Redis instance and the team's Python/Flask skill set. Kafka would require cluster provisioning, topic/partition design, schema registry setup, consumer offset management, and onboarding — a 6–8 week timeline before the first notification moves asynchronously.

## Consequences

### Pros

- **Immediate value.** Async notification processing can ship within the 2-week window, directly addressing request timeouts and cascading failures.
- **Low operational overhead.** No new distributed system to manage; Redis is already monitored and backed up.
- **Consumer groups provide retry.** Pending-entry lists and `XCLAIM` give us retry-with-backoff out of the box, solving the silent-failure problem.
- **Scales to 10x.** Single-node Redis handles our projected throughput. If needed, Redis Cluster scales horizontally without application-level partitioning changes.
- **WebSocket path is clear.** The same Redis Streams can fan out to WebSocket workers via `XREADGROUP`, supporting the real-time push requirement within two quarters.

### Cons

- **No native exactly-once.** Billing notifications require application-level idempotency and deduplication. This is additional code and a PostgreSQL write per billing notification, but it is a bounded, well-understood pattern.
- **Retention is bounded.** Messages are trimmed after processing, so we lose the ability to replay the full notification history from the stream. Audit relies on PostgreSQL, which is acceptable given our current architecture.
- **Single-node risk.** If the Redis instance goes down, notification processing halts. Mitigated by Redis persistence (AOF/RDB), replica promotion, and the fact that notification latency is already tolerated — a brief pause is preferable to today's synchronous blocking. Redis Sentinel or Redis Cluster provides automatic failover if this becomes unacceptable.
- **Not a long-term event-sourcing backbone.** If the platform later needs a full event-sourcing layer, CQRS, or multi-service event replay, Redis Streams will not serve that role and Kafka (or a similar log) would need introduction. This is acceptable: we solve today's problem with today's constraints, and a future event-sourcing requirement would be a separate ADR with different trade-offs.
- **Monitoring tooling is thinner.** Kafka ecosystems have richer observability (Confluent Control Center, Burrow, Kafka Exporter). Redis Streams monitoring requires custom metrics on stream length, pending count, and consumer lag — straightforward to add with a small Flask metrics endpoint.

## Alternatives Considered

### Apache Kafka

Kafka is the stronger technology for this problem in isolation: native exactly-once semantics, unbounded retention, mature consumer groups, proven at massive scale, and rich ecosystem tooling (schema registry, connectors, monitoring).

We reject it based on operational and timeline constraints:

- **No team experience.** None of the 6 engineers have operated Kafka. The learning curve for partition design, offset management, rebalancing, and failure modes is non-trivial and would consume the entire 2-week window before producing value.
- **Operational cost.** Even with managed Kafka (MSK, Confluent Cloud), the team must understand broker configuration, topic strategies, consumer group debugging, and scaling behavior. Managed does not mean zero-ops. The modest budget further constrains managed Kafka pricing at scale.
- **Over-engineering for current volume.** Our 10x scaling target (low thousands of msg/s) is well within Redis Streams' capability. Kafka's architectural advantages — log compaction, multi-tenant topic isolation, exactly-once transactions — solve problems we don't yet have and may never grow into given the team size.
- **2-week deadline is unachievable.** Responsible Kafka adoption requires cluster provisioning, topic and partition planning, schema registry, producer and consumer client configuration, monitoring setup, and team training. Realistic estimate: 6–8 weeks to first async notification.

If the team grows to include dedicated infrastructure engineers, or if the platform evolves toward event-sourcing/microservices at scale, Kafka should be revisited in a future ADR.