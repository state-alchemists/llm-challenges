# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our Flask monolith handles notifications (emails, webhooks) synchronously inside the HTTP request cycle. At 85,000 MAU and peak loads of ~500 req/s, this produces:

- **Request timeouts**: p99 latency spikes to 8 s because outbound SMTP/webhook calls block the response.
- **Silent failures**: No retry mechanism; dropped messages when providers are unavailable.
- **Cascading failures**: Slow webhook endpoints have exhausted the connection pool and degraded unrelated features twice this year.
- **Missing delivery guarantees**: Billing-critical events ("payment failed", "trial expired") currently have no at-least-once or exactly-once semantics.

We must decouple notification dispatch from the request cycle, introduce retry with exponential backoff, and guarantee exactly-once delivery for billing events. Within two quarters we also plan to add real-time WebSocket push notifications. The target is to support 10× traffic growth (≈5,000 req/s peak) without another re-architecture.

**Constraints**

- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Modest budget; managed Confluent Cloud is not affordable at target scale.
- Redis is already running in production (sessions, rate limiting).
- No Kafka operational experience on the team.
- Migration must deliver production value within two weeks.

## Decision

**We will use Redis Streams as the notification message bus.**

### Justification

The choice is driven by operational feasibility within a two-week window, team capacity, and existing infrastructure, while accepting manageable application-level complexity to achieve exactly-once semantics.

**Operational complexity**
Redis is already deployed, monitored, and backed up (AOF/RDB). Adding Streams requires only a configuration tuning pass (memory policies, `maxmemory` limits) and no new infrastructure, deployment artifacts, or on-call playbook. Self-hosting Kafka (the only budget-viable option) would demand broker provisioning, topic/ACL management, partition planning, consumer group rebalancing tuning, and disk/offset monitoring — a multi-week project for a team with no prior operational expertise and no dedicated SRE.

**Throughput**
Redis Streams on a single well-provisioned instance can sustain 100,000+ read/write operations per second. Our 10× peak target of ~5,000 messages/s, including retry and dead-letter traffic, is well within this headroom. Kafka offers higher aggregate throughput across a partitioned cluster, but that capacity is unnecessary for our projected scale and would force us to pay an operational tax we cannot absorb.

**Ordering guarantees**
Both systems provide strong ordering within a stream (Redis) or partition (Kafka). We will shard billing-critical notifications into a dedicated stream to preserve ordering per tenant without cross-traffic interference.

**Message retention**
Kafka’s disk-based retention is superior for long-term replay and audit, but notifications are ephemeral: once delivered and acknowledged they can be trimmed. Redis Streams support `MAXLEN` trimming and time-based eviction via `EXPIRE` on stream keys. We will cap notification streams at a safe memory budget (e.g., 24–48 hours of backlog) and archive billing outcomes into PostgreSQL for audit. This trade-off is acceptable given our modest budget and the absence of a long-term replay requirement.

**Consumer groups**
Redis Streams provide consumer groups with automatic message claiming (`XREADGROUP`, `XAUTOCLAIM`) for failed consumers. This is sufficient for our small fleet of worker processes. Kafka’s consumer group protocol is more sophisticated (cooperative rebalancing, static membership), but we do not need its advanced partition assignment semantics at our scale.

**Exactly-once semantics for billing notifications**
Kafka offers native exactly-once via idempotent producers and transactions. Redis Streams does not. We will implement exactly-once at the application layer, which is sufficient and idiomatic for our stack:

1. The producer writes each billing event to a Redis Stream with a deterministic idempotency key (e.g., `billing:<invoice_id>:<event_type>`).
2. Workers consume via `XREADGROUP`, process the notification, and insert a processed-marker row into PostgreSQL with a `UNIQUE` constraint on the idempotency key.
3. If a worker crashes after processing but before `XACK`, the message is redelivered; the duplicate PostgreSQL insert fails, and the worker acknowledges the message idempotently.

This pattern leverages our existing primary database, adds no new infrastructure, and provides the required exactly-once guarantee without relying on stream-native transactions.

**Migration timeline**
A Redis Streams pipeline can be deployed incrementally: a producer side-car in the Flask app, a small pool of consumers, and a dead-letter stream for exhausted retries. Because the team already operates Redis, this fits inside the two-week constraint. A Kafka deployment would require provisioning, testing failover behavior, and training the team before any production traffic could migrate — a timeline we cannot meet.

## Consequences

### Pros

- **Fast time-to-value**: Production async notifications within days, not weeks.
- **No new infrastructure**: Uses existing Redis nodes; reduces operational surface area.
- **Team leverage**: Engineers already know Redis commands, monitoring, and failure modes.
- **WebSocket synergy**: Redis Pub/Sub (or Streams read for stateful fan-out) aligns with the planned real-time push feature; Kafka would introduce a second system or require a bridging layer.
- **Sufficient throughput and latency**: Sub-millisecond produce/consume latency and headroom for 10× load.

### Cons

- **Memory-bound retention**: Long backlogs or large dead-letter queues risk memory pressure. Mitigated by aggressive `MAXLEN` trimming and archiving outcomes to PostgreSQL.
- **Application-level exactly-once**: Billing de-duplication logic must be correct and tested; a bug could duplicate or drop a critical event. Mitigated by `UNIQUE` constraints and idempotency keys in PostgreSQL.
- **Less mature ecosystem**: No built-in stream processing framework (e.g., Kafka Streams, ksqlDB). Complex transformations will require custom Python workers.
- **Single-node risk**: Our current Redis setup is not clustered; a node failure would pause notification processing until failover. Mitigated by Redis Sentinel or by migrating to Redis Cluster in a future quarter if needed. Given our RTO tolerance for notifications (minutes, not seconds), this is acceptable.
- **Future re-architecture risk**: If we grow far beyond 10× or require months of retention, we may eventually outgrow Redis Streams and migrate to Kafka. We accept this risk because the alternative — betting the present on Kafka — fails the immediate operational and timeline constraints.

## Alternatives Considered

### Apache Kafka

Kafka was rejected because the operational burden exceeds our team’s capacity and budget constraints:

- **Operational complexity**: Self-hosted Kafka requires broker management, partition sizing, consumer rebalancing tuning, and disk/offset monitoring. With no dedicated infrastructure engineer, this would consume a disproportionate share of a 6-person team.
- **Timeline**: A safe Kafka deployment, including failover testing and team onboarding, cannot be completed in two weeks.
- **Cost**: Managed Confluent Cloud is explicitly out of budget. Self-hosting avoids licensing costs but imposes the hidden cost of engineering time and on-call load.
- **Exactly-once**: While Kafka’s idempotent producers and transactions provide stronger native exactly-once semantics, realizing this benefit requires correct producer and consumer configuration that our team has no experience maintaining.
- **10× growth**: Kafka’s scaling story is stronger, but Redis Streams already satisfies our concrete 10× target (≈5,000 msg/s), making Kafka’s extra headroom speculative rather than required.
