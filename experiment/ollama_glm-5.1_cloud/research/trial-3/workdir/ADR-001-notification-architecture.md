# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users who create ~2M tasks per month, with peak traffic of ~500 requests per second during business hours. The notification module — responsible for sending emails and webhooks on task updates, assignments, and completions — currently runs synchronously inside the HTTP request cycle. This has led to:

1. **Request timeouts.** Average latency of 800 ms, spiking to 8 s during peak hours.
2. **Silent failures.** No retry or dead-letter queue; notifications are dropped when an email provider or webhook endpoint is down.
3. **Cascading failures.** Two incidents this year where a slow webhook endpoint exhausted the connection pool, taking down unrelated features.
4. **No delivery guarantees.** Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once; the current system offers no such guarantee.

We need to decouple notifications from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible), and prepare for real-time WebSocket push within two quarters — all while handling 10× traffic growth without re-architecting.

Key constraints:

- **Team:** 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Existing stack:** Redis already in production for sessions and rate limiting; no Kafka experience on the team.
- **Time box:** Must deliver value within 2 weeks of starting; no multi-month migration.
- **Budget:** Modest — managed Confluent Cloud at full scale is not affordable today.
- **Correctness:** Exactly-once semantics required for billing notifications.

Two candidates emerged: **Apache Kafka** and **Redis Streams**.

## Decision

We will use **Redis Streams** as the message backbone for the notification subsystem.

### Justification

The deciding factor is not raw capability — Kafka is the more powerful system in isolation — but the intersection of our constraints and operational reality.

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| **Throughput** | 100 K–500 K msg/s per node (sufficient for our 10× target of ~5 K msg/s) | Millions of msg/s per cluster |
| **Ordering guarantees** | Per-stream strict ordering (all notifications for a given entity type ordered) | Per-partition ordering (requires careful partition key design) |
| **Message retention** | Time-based or MAXLEN-based trimming; adequate for notification replay windows (hours–days) | Configurable long-term retention (days–weeks by default) |
| **Consumer groups** | `XGROUP` / `XREADGROUP` / `XPENDING` — supports group consumption, claim, and backlog replay | Mature consumer group protocol with offset management and partition rebalancing |
| **Exactly-once semantics** | At-least-once delivery; exactly-once requires idempotent consumers | Transactional producer + idempotent consumer API; true EOS possible but complex to implement correctly |
| **Operational complexity** | Already operated; adding streams is a config change, not a new service | New distributed system: brokers, ZooKeeper or KRaft, partition management, monitoring |
| **Team familiarity** | High — Redis is already in production and on-call runbooks | None — no prior operational experience |
| **Setup time** | 1–3 days (stream creation, consumer group, worker skeleton) | 2–4 weeks minimum for a team with no Kafka experience (cluster provisioning, security, monitoring, on-call) |
| **Cost** | Already budgeted; marginal memory/CPU increase for streams | Self-hosted: significant ops cost; managed: exceeds budget at scale |

**Why this is the right call for us:**

1. **We can ship in days, not weeks.** Redis Streams require a single `XADD` from the Flask monolith and a `XREADGROUP` worker — both well-understood patterns. Kafka would need cluster provisioning, security configuration, and a non-trivial client library before the first message flows.
2. **We already operate Redis.** Adding streams to the existing instance (or a dedicated Redis node) does not introduce a new failure domain or on-call burden. Kafka would add a distributed system we have no experience debugging at 3 AM.
3. **Throughput is not our bottleneck.** Our 10× growth target is ~5,000 notifications per second. Redis Streams handle two orders of magnitude more than that. Kafka's throughput advantage is real but irrelevant at our scale.
4. **Exactly-once for billing is achievable with Redis.** Kafka's transactional EOS is powerful but notoriously difficult to implement correctly — even experienced teams often fall back to idempotent consumers. With Redis Streams, we will guarantee at-least-once delivery via `XREADGROUP` with explicit `XACK`, and enforce exactly-once processing through idempotency keys on the consumer side (deduplication table in PostgreSQL). This is the same pattern any team would need regardless of the broker, since true end-to-end exactly-once requires idempotent writes to the downstream system (email provider, billing API) — something no message broker can guarantee alone.

## Consequences

### Pros

- **Fast time to value.** We can implement async notification dispatch within the 2-week window: `XADD` in the request handler, `XREADGROUP` worker process, and a dead-letter stream for failed deliveries.
- **No new infrastructure.** Redis is already monitored, backed up, and on-call-ready. We avoid introducing a new distributed system with its own failure modes.
- **Lower cognitive load.** The team can reason about streams using the same mental model they use for Redis lists and pub/sub. Kafka's partition/offset/log-compaction model would require significant learning.
- **Consumer group support.** `XGROUP` and `XPENDING` give us group-based consumption, message claiming for failed workers, and backlog replay — everything we need for retry with exponential backoff.
- **WebSocket path.** Redis Pub/Sub + Streams can feed a WebSocket fan-out layer (e.g., via a thin Socket.io or FastAPI process) within the same infrastructure, satisfying the real-time push requirement.
- **Cost-neutral.** Marginal increase in Redis memory usage; no new licensing or hosting costs.

### Cons

- **Message retention is limited.** Redis Streams trim by count or time; we cannot retain notification history indefinitely in the stream itself. We will archive processed notifications to PostgreSQL for audit and replay, which is appropriate regardless of the broker.
- **No native partition rebalancing.** Kafka rebalances consumers across partitions automatically when a consumer joins or leaves. With Redis Streams, we must implement consumer coordination (e.g., using a consistent-hash ring or a simple round-robin claim strategy) if we scale beyond a single worker per stream. This is manageable at our scale but becomes a consideration past ~20 consumers.
- **At-least-once, not exactly-once, at the broker level.** Redis guarantees at-least-once delivery within a consumer group. Exactly-once processing requires application-level idempotency — we accept this and implement it explicitly via deduplication keys in PostgreSQL.
- **Single-node availability.** A standalone Redis instance is a single point of failure. We will mitigate this by running Redis with persistence (AOF + RDB) and configuring automatic restarts. If availability requirements grow, we can migrate to Redis Sentinel or Redis Cluster without changing the stream API.
- **Scale ceiling.** If the platform grows beyond ~500 K msg/s or requires multi-datacenter replication, Redis Streams will need re-evaluation. At that point, the team will have grown and will have the operational maturity to adopt Kafka.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for event streaming and would serve our throughput and retention needs at any scale. Its consumer group protocol, partition-based parallelism, and transactional exactly-once semantics are superior to Redis Streams in isolation.

**Why we reject it for now:**

- **Operational cost exceeds our capacity.** A 6-person team with no Kafka experience and no dedicated infrastructure engineer cannot safely operate a Kafka cluster in production. Managed Kafka (Confluent Cloud, AWS MSK) reduces the ops burden but exceeds our budget at scale and still requires significant learning.
- **Setup time violates the constraint.** Even with a managed service, integrating Kafka (schema design, producer configuration, consumer group tuning, monitoring) would take 3–4 weeks before the first notification is delivered asynchronously — well beyond our 2-week window.
- **Over-engineering for our scale.** At ~5 K notifications per second (our 10× target), Redis Streams provide ample headroom. Kafka's architectural advantages (infinite retention, partition rebalancing, log compaction) solve problems we do not yet have.

Kafka remains the right migration target if and when we outgrow Redis Streams. The stream-based architecture we are building makes this migration a broker swap, not a rewrite — consumers read from a stream and write idempotently; the broker is an implementation detail.

### Other alternatives briefly considered

- **RabbitMQ:** Good retry and dead-letter support, but introduces a new broker (we do not run it today) and lacks the native stream semantics that map cleanly to our fan-out and replay needs. Would also exceed the 2-week setup window.
- **Database-backed queue (Postgres `SKIP LOCKED`):** Viable for low throughput, but would increase write load on our already-burdened primary and does not support fan-out to WebSocket workers naturally.
- **AWS SQS / SNS:** Adds a cloud-provider dependency and introduces latency (polling model). Consumer group semantics are weaker than Redis Streams' `XREADGROUP`. Would also require IAM and VPC configuration outside our current operational model.