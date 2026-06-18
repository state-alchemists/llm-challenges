# ADR-001: Notification Subsystem Architecture

## Status

**Proposed**

## Context

Our Flask monolith currently sends email and webhook notifications synchronously inside the HTTP request cycle. At 85,000 MAU and peak loads of ~500 req/s, this design produces average latencies of 800 ms (spikes to 8 s), silent drops on downstream failures, and cascading outages when slow webhook endpoints exhaust our connection pools.

We must move to an async, decoupled notification pipeline that satisfies:

- **At-least-once delivery** for all notifications, with **exactly-once semantics** for billing-critical events (trial expiry, payment failure).
- **Retry with exponential backoff** and visibility into dead-lettered messages.
- **Headroom for 10× traffic growth** (≈5,000 req/s peak) without a future re-architecture.
- **Real-time WebSocket push** within the next two quarters.
- **Delivery within two weeks** by a six-person engineering team (three senior, three mid-level) with **no dedicated infrastructure engineer**.
- **Modest budget** that rules out premium managed offerings such as Confluent Cloud at full scale.

We evaluated two candidate streaming platforms: **Apache Kafka** and **Redis Streams**.

## Decision

**Adopt Redis Streams as the notification event bus.**

We will use Redis Streams (introduced in Redis 5.0) as the primary message-oriented middleware for asynchronous notification dispatch. Producers will `XADD` notification events into typed streams (e.g., `stream:email`, `stream:webhook`). Consumers will run as independent worker processes using `XREADGROUP` with consumer groups, relying on the Pending Entries List (PEL) for automatic claim-and-retry semantics. Exactly-once processing for billing events will be enforced at the application layer using idempotency keys stored in our existing PostgreSQL database, combined with `XACK`-based acknowledgment after a successful, committed write to the downstream provider.

## Consequences

### Positive

1. **Time-to-value (< 2 weeks)** – The team already operates Redis for sessions and rate-limiting. Adding Streams requires no new infrastructure, no new deployment artifacts, and minimal learning curve. A senior engineer can have a prototype running in days.
2. **Operational simplicity** – Redis is a single binary with straightforward observability (MEMORY STATS, INFO, LATENCY DOCTOR). There are no brokers, ZooKeeper / KRaft clusters, partition rebalancing storms, or ISR management to tune.
3. **Throughput adequate for 10× growth** – A single modern Redis instance can sustain tens of thousands of stream operations per second. Our 10× target (≈5,000 req/s) sits comfortably within that envelope.
4. **Ordering and grouping** – Redis Streams provides total ordering within a single stream key. Consumer groups (`XGROUP CREATE`, `XREADGROUP`) give us horizontally scalable workers with automatic shard balancing via `XCLAIM`, satisfying our need for concurrent, resilient consumers.
5. **Retention flexibility** – We can cap stream length by count (`MAXLEN`) or by time, and because notification payloads are small metadata (not large blobs), trimming to a few million entries keeps memory usage modest while supporting retries over a multi-day window.
6. **WebSocket readiness** – Because Redis is already in our stack, the subsequent WebSocket real-time requirement can reuse the same Redis deployment (pub/sub or secondary streams), avoiding yet another infrastructure component.
7. **Cost** – ElastiCache for Redis or a self-managed EC2 instance fits our modest budget. There is no per-partition or per-broker metered charge that balloons with throughput.

### Negative / Risks

1. **Exactly-once is application-enforced** – Redis Streams does not offer Kafka-style idempotent producers or cross-stream transactions. We must implement deduplication ourselves: an `idempotency_key` column in PostgreSQL, checked before dispatch, ensures billing events are processed once even if a worker crashes between the downstream send and `XACK`.
2. **Durability ceiling** – Redis defaults to an in-memory primary dataset. While AOF (everysec) and RDB snapshots mitigate loss, a catastrophic failure before fsync can lose the last second of stream data. For billing-critical events we will supplement with synchronous `WAIT` replication or a short-lived Postgres outbox table, trading a little latency for durability.
3. **Long-term retention cost** – Unlike Kafka’s log-segment design, which stores months of data cheaply on disk, Redis Streams reside in RAM. We will therefore enforce aggressive `MAXLEN` trimming (retaining only the retry window plus safety margin) and archive audit trails to S3 via a nightly batch job.
4. **Single-node bottleneck at extreme scale** – Beyond our 10× horizon, vertical scaling hits limits. Migrating to Redis Cluster or eventually to Kafka remains a future option once we have staffing and budget for a dedicated infrastructure role.

## Alternatives Considered

### Apache Kafka

Kafka is the gold-standard distributed event log. It offers superior disk-based retention, native partitioning, and mature exactly-once semantics via idempotent producers and transactions (`enable.idempotence=true`, `transactional.id`). Its consumer-group protocol is battle-tested for massive fan-out and replay.

**Why we rejected it:**

1. **Operational complexity exceeds our staffing** – Self-hosting Kafka requires managing brokers, controller election (ZooKeeper or KRaft), replication ISR lists, partition rebalancing, and client-side offset management. Our team has **zero prior Kafka experience** and **no dedicated infrastructure engineer** to own on-call incidents. Even AWS MSK offloads broker patching, not topic design, consumer lag diagnosis, or client misconfiguration.
2. **Two-week timeline is incompatible with safe adoption** – Learning to operate Kafka confidently enough to host billing-critical workflows in production in under two weeks is an unacceptable risk.
3. **Budget constraints** – Managed Confluent Cloud is explicitly ruled out. MSK or bare-metal EC2 introduces fixed baseline costs (minimum three broker instances) that strain a modest budget for a workload that is currently measured in thousands, not millions, of events per second.
4. **Overkill for current scale** – At 500 req/s peak (5,000 req/s target), Kafka’s throughput advantage is irrelevant. Redis Streams handles this load with headroom to spare.
5. **End-to-end exactly-once still requires application work** – Kafka guarantees exactly-once broker-side, but our consumers ultimately call external SMTP and HTTP endpoints that are not transactional with Kafka. Application-level idempotency (the same dedup table we would build for Redis) is still required, diluting Kafka’s theoretical advantage for this use case.

**Verdict:** Kafka is architecturally elegant but imposes a cost and complexity tax that our team size, budget, and deadline cannot absorb safely. We will revisit Kafka when notification volume crosses the threshold where Redis Cluster becomes painful or when we hire infrastructure expertise.
