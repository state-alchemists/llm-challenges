# ADR-001 — Adopt Redis Streams for the Asynchronous Notification Subsystem

**Status**: Proposed

---

## Context

Our Python/Flask monolith currently sends email and webhook notifications synchronously inside the HTTP request cycle. At 85,000 MAU and ~500 req/s peak, this has produced four correlated failure modes:

1. **Request timeouts** — notification I/O blocks responses; p99 latency spikes to 8 s during business hours.
2. **Silent failures** — downstream provider outages drop notifications with no retry or dead-letter mechanism.
3. **Cascading failures** — slow webhook endpoints have exhausted the Flask connection pool twice this year, taking down unrelated features.
4. **No delivery guarantees** — billing-critical events (trial expiry, payment failure) are not guaranteed even once, let alone exactly once.

We must move notification dispatch to an async pipeline with the following non-negotiables:

- Decouple notification work from the HTTP request cycle.
- Retry with exponential backoff.
- At-least-once delivery for all events; exactly-once semantics for billing-critical events.
- Capacity for 10× traffic growth (from ~500 to ~5,000 req/s peak) without re-architecting.
- Foundation for real-time WebSocket push notifications within two quarters.
- Delivery within two weeks of engineering time before we see production value.

Constraints shaping this decision:

- Engineering team: six people (three senior, three mid-level), **no dedicated infrastructure engineer**.
- Redis is already deployed in production (sessions, rate limiting).
- **No team member has prior production experience with Apache Kafka**.
- Budget is modest; managed Confluent Cloud is not financially viable today.

---

## Decision

> We will adopt **Redis Streams** as the message backbone for the asynchronous notification pipeline.

This decision prioritizes operational leverage over theoretical feature completeness. The team already operates Redis for stateful workloads; extending it to durable stream processing eliminates the bootstrap cost and ongoing operational burden of a brand-new distributed system. The resulting architecture will use Redis Streams for queuing and fan-out, with application-level idempotency (PostgreSQL unique-constraint table) guaranteeing exactly-once processing of billing events.

---

## Consequences

### Positive

- **Immediate time-to-value**: Using existing Redis instances and the `redis-py` client (which has supported Streams since v3.0), we can have a basic producer/consumer pair running in staging within days. This satisfies the two-week delivery mandate.
- **Low operational complexity**: There is no new service to provision, monitor, or tune. Replication, failover, and backup policies reuse the operational runbook we already maintain for Redis sessions.
- **Sufficient throughput headroom**: Redis Streams routinely benchmarks at >100,000 messages/sec read/write on a single node for small payloads. Our 10× target of ~5,000 req/s leaves enormous margin before vertical scaling becomes necessary.
- **Natural path to WebSocket push**: Because Redis is already in the stack, later real-time broadcasts can reuse Redis Pub/Sub or dedicated streams without introducing yet another infrastructure dependency.
- **Consumer-group primitives are adequate**: Redis Streams provides consumer groups (`XGROUP`, `XREADGROUP`), pending-entry lists, and automatic message claiming (`XCLAIM`) for crashed consumers. These cover our single-service, fixed-partition consumption model without the rebalancing complexity of a full consumer-group coordinator.

### Negative

- **Memory-bound retention**: Redis Streams are stored in memory. Message retention is controlled by capped-stream limits (`MAXLEN`) or manual `XTRIM`, not by the time/size-based log retention that Kafka offers on disk. If an outage prevents consumers from running, unbounded stream growth risks an OOM condition unless strict caps are enforced.
- **Limited observability tooling**: There is no out-of-the-box equivalent to Kafka’s consumer-lag dashboards or rebalance metrics. We will need to instrument pending-message counts (`XPENDING`) ourselves and alert on consumer staleness.
- **Horizontal scaling is not transparent**: Kafka scales throughput by adding brokers and partitions. Redis Streams on a single primary can only scale vertically. If we materially exceed the 10× growth target, we will need to shard streams by tenant or event category—i.e., re-architect.
- **Exactly-once is an application concern**: Redis Streams offers no idempotent-producer or transactional-cross-stream semantics. Exactly-once billing processing depends entirely on our idempotency-table implementation in PostgreSQL. A bug in that layer can duplicate or drop a billing event.
- **Durability nuance**: By default, Redis is optimized for cache-like workloads. We must explicitly enable and tune AOF (`appendfsync everysec`) and RDB snapshots to prevent message loss on an unclean restart of the Redis primary.

---

## Alternatives Considered

### Apache Kafka

Kafka is the architecturally purer choice for event streaming. It offers disk-persistent, replicated topic logs; mature consumer-group rebalancing; time- and size-based retention; and native idempotent producers with transactional delivery, which bring "exactly-once" semantics closer to the broker layer than Redis can.

We rejected Kafka for this stage because the **operational mismatch with our constraints is fatal**:

- **Operational complexity** is incompatible with a six-person team that lacks an infrastructure engineer. Running a production Kafka cluster (even KRaft mode) requires expertise in broker tuning, partition balancing, replication-factor management, and failure recovery. A misconfigured cluster would replicate the very cascading-failure risk we are trying to eliminate.
- **No prior experience** means the two-week delivery window is unrealistic. The team would spend the first week learning broker deployment and client semantics before writing a single notification worker.
- **Budget rules out managed relief**: Because Confluent Cloud (or Amazon MSKS at scale) is not affordable today, we cannot outsource the operational complexity.
- **Throughput is currently over-provisioned**: Kafka’s headline strength is horizontal scaling to millions of messages per second. Our 10× ceiling of ~5,000 req/s is well within Redis Streams’ single-node capacity, so we would be paying operational complexity for headroom we do not yet need.

We would revisit Kafka if we grow past ~20,000 sustained notifications/sec, acquire a platform/infrastructure role, or our budget expands to cover a managed offering. At that point, the migration path is well-understood: producers write to both systems during a cutover window while consumers drain the Redis backlog.
