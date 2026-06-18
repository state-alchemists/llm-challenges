# ADR 001 — Notification Subsystem Message Transport

- **Status**: Proposed
- **Date**: 2026-06-19
- **Deciders**: Engineering team (3 senior, 3 mid-level)
- **Context tags**: notifications, messaging, redis, kafka, architecture

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails and webhooks triggered by task lifecycle events — synchronously inside the HTTP request cycle. This has caused three classes of failure:

1. **Request timeouts.** Average notification latency is 800 ms, spiking to 8 s during peak hours because the web process blocks on SMTP and HTTP webhook calls before returning a response.
2. **Silent data loss.** When an email provider or webhook endpoint is down, the notification is dropped with no retry or dead-letter queue.
3. **Cascading outages.** Two incidents this year where a slow webhook consumer exhausted the connection pool, degrading unrelated features.

The business also requires **exactly-once delivery for billing-critical notifications** ("trial expired", "payment failed") — a guarantee the current system cannot make.

Near-term needs: decouple notifications from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), and support real-time WebSocket push within two quarters. Long-term: handle 10× traffic growth without re-architecting.

**Constraints:**

- 6-person engineering team, no dedicated infrastructure engineer.
- Redis already in production for sessions and rate limiting; team has operational experience with it.
- No prior Kafka experience on the team.
- Must deliver production value within 2 weeks of starting migration.
- Modest budget — managed Confluent Cloud at full scale is not affordable today.

## Decision

We will use **Redis Streams** as the message transport for the notification subsystem.

Notification producers write to Redis Streams (`XADD`). A consumer group (`XREADGROUP`) processes events with retry and exponential backoff via `XPENDING` / `XCLAIM`. Billing-critical notifications use a dedicated stream with application-level idempotency keys to achieve exactly-once delivery semantics. Redis Pub/Sub will layer in alongside Streams for real-time WebSocket fan-out when that phase ships.

## Rationale

**Throughput is well within Redis Streams' capacity.** Current peak is ~500 req/s; even with 3 notifications per request (1,500 msgs/s) and a 10× growth target (15,000 msgs/s), Redis Streams on a single node handles this comfortably — Redis' single-threaded write path benchmarks at ~100K ops/s. Kafka's headroom (millions of msgs/s across a cluster) is orders of magnitude beyond what we need and does not justify its operational cost.

**Time to value is the binding constraint.** The team must deliver working async notifications within 2 weeks. Redis Streams runs on infrastructure we already operate; Kafka requires provisioning a new cluster (or managed service), learning topic/partition design, configuring monitoring, and building operational runbooks — none of which the team has experience with. Two weeks is insufficient to stand up Kafka safely.

**Operational complexity is the deciding factor.** A 6-person team without a dedicated infrastructure engineer cannot absorb the burden of running Kafka — broker management, partition rebalancing, ZooKeeper/KRaft quorum, consumer lag monitoring, and topic lifecycle are non-trivial even with managed offerings. Redis Streams adds negligible operational surface: it runs on our existing Redis instance, uses our existing monitoring, and requires no new deployment topology.

**Exactly-once for billing is achievable at the application layer.** Neither Kafka nor Redis Streams can guarantee exactly-once delivery to an external system (SMTP, webhook endpoint) — both require idempotent consumers and deduplication at the handler level. Kafka's transactional exactly-once semantics apply to internal stream processing, not to side-effecting delivery. We will implement idempotency keys (stored in PostgreSQL alongside the notification record) and consumer-side deduplication. This is the correct semantics for "exactly-once delivery to an external service," and it works identically regardless of transport.

**Redis Pub/Sub + Streams is a natural fit for WebSocket push.** The two-quarter WebSocket goal requires per-connection fan-out. Redis Pub/Sub provides low-latency message dispatch to connected application servers, while Streams provide the durable, ordered backlog for offline catch-up. Kafka is designed for high-throughput partitioned consumption, not per-connection pub/sub — using it for WebSocket fan-out would require an awkward consumer-per-connection model or an external fan-out layer.

## Alternatives Considered

- **Apache Kafka** — Rejected because the operational burden is unjustifiable for our scale and team. Kafka excels at very high throughput (millions of msgs/s), multi-topic event routing, long-term log retention, and cross-service event sourcing — none of which are our primary requirements. The 2-week delivery window, team's lack of Kafka experience, and absence of a dedicated infrastructure role make Kafka a net negative at this stage. We would revisit Kafka if throughput requirements exceed ~500K msgs/s, we need multi-service event sourcing, or the team grows to include dedicated platform infrastructure engineers. At that point, managed Confluent or AWS MSK would reduce the ops burden enough to reconsider.

## Consequences

- **Positive**
  - Notification processing is fully decoupled from the HTTP request cycle, eliminating request timeouts and cascading failures caused by slow external endpoints.
  - Retry with exponential backoff is built into the consumer group model (`XCLAIM` with idle-time tracking); dead-letter handling is straightforward to add by moving unclaimable messages to a secondary stream.
  - Billing notifications get exactly-once delivery via application-level idempotency keys — the same pattern we would need on top of Kafka.
  - Operational surface stays minimal: one more data structure on an existing Redis instance, no new services to deploy or monitor.
  - Clear path to WebSocket push: Redis Pub/Sub for live fan-out, Streams for durable catch-up.
  - 2-week delivery window is realistic — the team can ship a working producer/consumer in the first sprint using existing Redis and Python libraries (`redis-py` supports Streams natively).

- **Negative**
  - Redis Streams' retention is capped by memory. If consumers fall behind and backlog grows beyond `MAXLEN`, messages are trimmed before delivery. We mitigate this with generous `MAXLEN` thresholds, consumer lag alerting, and a persistent `notifications` table in PostgreSQL as the durable source of truth (Streams are a transient dispatch layer, not the system of record).
  - No native exactly-once semantics in Redis. Idempotency and deduplication are our responsibility. This is acceptable because external delivery (email, webhook) requires application-level idempotency regardless of transport — the same deduplication logic would be needed on Kafka.
  - Single Redis node is a single point of failure for notification dispatch. We already plan to run Redis in a primary-replica configuration with automatic failover (consistent with our existing production topology). If Redis becomes unavailable, notifications remain persisted in PostgreSQL and are dispatched once Redis recovers — no data loss, only delivery delay.
  - Redis Streams does not support partitioned parallelism within a single stream the way Kafka topics with multiple partitions do. For our 15K msgs/s target, a single stream is sufficient; if we eventually exceed this, we can shard by notification type into multiple streams before considering a Kafka migration.
  - Migrating to Kafka later would require rewriting producers and consumers. This is a bounded cost (one producer, a small number of consumer handlers) and is an acceptable trade-off for the operational simplicity we gain today.

- **Follow-ups**
  - Implement idempotency key storage in PostgreSQL for billing-critical notifications (prevents duplicate delivery across consumer restarts).
  - Set up consumer lag alerting on `XPENDING` counts — alert if pending messages exceed threshold for longer than N minutes.
  - Define `MAXLEN` policy per stream based on expected throughput and acceptable backlog depth.
  - Add a dead-letter stream for messages that exceed max retry count.
  - Document the producer/consumer contract (stream key naming, message schema, idempotency key convention) in the project wiki.
  - Evaluate Redis Sentinel or Cluster failover configuration to ensure notification dispatch survives a primary node failure.