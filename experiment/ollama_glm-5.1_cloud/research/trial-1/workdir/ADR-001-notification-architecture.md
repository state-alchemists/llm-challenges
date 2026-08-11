# ADR-001: Notification Subsystem Architecture

- **Status**: Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users with ~2M tasks created per month and peak traffic of ~500 requests per second. The notification module — which sends emails and webhooks on task updates, assignments, and completions — currently runs synchronously inside the HTTP request cycle. This has caused four recurring problems:

1. **Request timeouts**: Notifications block the response. Average latency is 800ms, spiking to 8s during peak hours.
2. **Silent failures**: When an email provider or webhook endpoint is down, notifications are silently dropped — no retry, no dead-letter queue.
3. **Cascading failures**: Two incidents this year where a slow webhook endpoint exhausted the database connection pool, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") require exactly-once delivery, but the current system provides none.

We need to decouple notification delivery from the HTTP request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), prepare for real-time WebSocket push notifications within two quarters, and handle 10× traffic growth without re-architecting.

**Constraints:**

- Engineering team of 6 (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis already in production for session storage and rate limiting.
- No Kafka experience on the team.
- Setup and migration must deliver value within 2 weeks.
- Modest budget — managed Confluent Cloud at full scale is cost-prohibitive today.
- Exactly-once semantics required for billing notifications.

## Decision

We will use **Redis Streams** as the message broker for the notification subsystem.

Redis Streams provides sufficient throughput and ordering guarantees for our scale (current 500 req/s, target 5,000 req/s), consumer groups for parallel processing, and at-least-once delivery with acknowledgments — all on infrastructure the team already operates. Exactly-once semantics for billing notifications will be enforced at the application layer via idempotency keys, which is the recommended approach regardless of the broker chosen.

## Consequences

**Positive:**

- **Minimal operational overhead**: Redis is already running in production. No new cluster, no new monitoring stack, no new failure domain. The team's existing Redis operational knowledge applies directly.
- **Fast time-to-value**: Redis Streams requires adding `XADD`/`XREADGROUP` commands to the existing codebase — achievable well within the 2-week constraint. A dedicated notification worker process can begin draining the stream and delivering retries within days.
- **Adequate throughput**: A single Redis instance handles hundreds of thousands of messages per second. Our 10× growth target (5,000 req/s peak, with each request producing 1–3 notification events) sits comfortably within this capacity.
- **Consumer groups**: Redis Streams' `XREADGROUP` with `XACK` provides partitioned, parallel consumption with per-consumer delivery tracking — the same fundamental model as Kafka consumer groups, suitable for our worker pool.
- **Per-stream ordering**: Messages within a single stream are strictly ordered by insertion. Grouping billing notifications into a dedicated stream preserves the ordering required for events like "payment failed" → "payment retried."
- **Built-in pending entries list (PEL)**: Unacknowledged messages are tracked via `XPENDING`, enabling dead-letter detection and retry with exponential backoff without external state.
- **Cost**: No additional infrastructure spend beyond the existing Redis instance (which may need a memory increase, far cheaper than a Kafka cluster).

**Negative:**

- **No native exactly-once semantics**: Redis Streams offers at-least-once delivery. Exactly-once for billing notifications must be implemented at the application layer (idempotency keys on the consumer side, deduplication tables in PostgreSQL). This is standard practice — even Kafka's transactional exactly-once requires consumer-side idempotency to be truly safe — but it is additional application logic we must build and test.
- **Message retention bounded by memory**: Redis Streams retains messages up to a configurable `MAXLEN` or time threshold. If consumers fall behind beyond the retention window, messages are trimmed and lost. We must size retention conservatively and monitor the PEL depth. Kafka's disk-based retention is more forgiving here.
- **Single-node availability**: Our Redis is not currently in a cluster or Sentinel configuration. A Redis outage halts all notification processing. We will need to add Redis Sentinel or a managed Redis with automatic failover (e.g., ElastiCache) before this system is production-critical.
- **Limited tooling ecosystem**: Kafka has a richer ecosystem of monitoring tools (Kafka UI, Burrow, Cruise Control), schema registries, and connector frameworks. Redis Streams lacks equivalent tooling; we will build custom dashboards on `XINFO`/`XPENDING` metrics.
- **Replay semantics are weaker**: Redis Streams does not support arbitrary offset-based replay as naturally as Kafka. Re-processing from a timestamp is possible via `XREAD` with `XRANGE`, but it is less ergonomic than Kafka's partition offset model.

**Follow-ups:**

- Implement idempotency-key deduplication for billing notifications (PostgreSQL table keyed on `notification_type + entity_id + idempotency_key`).
- Add Redis Sentinel or migrate to managed Redis with failover before promoting the notification worker to production-critical status.
- Build monitoring for stream depth (`XLEN`), consumer lag (`XPENDING`), and dead-letter rate.
- Design a dedicated `billing-notifications` stream separate from the general `notifications` stream to isolate billing event ordering and retention policies.
- Allocate 2–3 days in the next quarter to prototype WebSocket delivery, confirming that the stream → fan-out model works for real-time push.

## Alternatives Considered

**Apache Kafka** — We rejected Kafka for this phase of the project. Kafka's strengths — disk-based retention, native exactly-once transactional semantics, multi-datacenter replication, and a mature ecosystem — are real, but they do not justify the cost for our current constraints:

- **Operational complexity**: A production Kafka deployment requires broker configuration, partition strategy, replication factor tuning, and monitoring (under-replicated partitions, consumer lag via Burrow or similar). With no Kafka experience on the team and no dedicated infra engineer, the operational risk is significant. A misconfigured Kafka cluster can cause exactly the kind of outage we are trying to prevent.
- **Setup time**: Even with managed Kafka (e.g., AWS MSK, Confluent Cloud), integrating a new message broker, writing producers/consumers, and validating delivery semantics would take 3–4 weeks — exceeding the 2-week constraint. Self-managed Kafka would take longer.
- **Cost**: Managed Kafka pricing at our message volume (estimated 5–15M notification events per month at 10× growth) would add $500–$1,500/month at minimum. This is disproportionate to the problem we are solving.
- **When Kafka would win**: If our throughput grows beyond what a single Redis instance can handle (hundreds of thousands of messages per second), or if we need durable event sourcing with multi-day replay windows, or if we expand to multi-region deployments, we should revisit Kafka. At that point the team will have operational maturity from running Redis Streams and can evaluate whether the added complexity is warranted.