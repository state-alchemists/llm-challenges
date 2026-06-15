# ADR-001: Notification Architecture — Redis Streams

**Status:** Proposed

---

## Context

Our SaaS project-management platform currently sends email and webhook notifications synchronously inside the Flask HTTP request cycle. At 85,000 MAU and peak loads of ~500 req/s, this has produced:

- **Request timeouts**: average notification latency of 800 ms, spiking to 8 s during peaks.
- **Silent failures**: provider or endpoint outages drop notifications with no retry mechanism.
- **Cascading failures**: slow webhook endpoints have exhausted connection pools and taken down unrelated features (two incidents this year).
- **No delivery guarantees**: billing-critical events (trial expired, payment failed) currently lack even at-least-once semantics.

We must decouple notification dispatch from the request cycle, add retry with exponential backoff, and guarantee exactly-once delivery for billing events. We also plan real-time WebSocket push within two quarters and need to absorb 10× traffic growth without re-architecting.

**Constraints**

- Engineering team: 6 people (3 senior, 3 mid-level), **no dedicated infrastructure engineer**.
- Redis is already in production (sessions, rate limiting).
- **No Kafka experience** on the team today.
- Migration must deliver value within **two weeks**.
- Budget is modest; managed Confluent Cloud is not viable at full scale.

---

## Decision

**Adopt Redis Streams as the notification message bus.**

Redis Streams satisfies our functional requirements while respecting the hard constraints of team size, operational maturity, and timeline. The throughput headroom, existing operational footprint, and low migration risk outweigh the richer streaming primitives of Kafka for our current stage.

### Justification by property

| Property | Redis Streams (chosen) | Apache Kafka (rejected) |
|---|---|---|
| **Peak throughput** | ~100 k messages/sec per node — ample for 500 req/s today and 5,000 req/s at 10× growth. | Millions of messages/sec; superior for hyperscale, but over-provisioned for our volume. |
| **Ordering guarantees** | Strict FIFO within a single stream key; sufficient because notification ordering is per-user or per-workspace. | Partition-level ordering; stronger scaling semantics but requires careful partitioning design we do not have time to validate. |
| **Message retention** | Memory-bounded with configurable `MAXLEN` / `XTRIM`. Given our message volume (~2 M tasks/month plus retries), a moderate cap plus consumer ACKs keeps memory predictable. | Disk-based, effectively unbounded retention by default; better for long-term replay but adds storage cost and operational surface. |
| **Consumer groups** | Native `XREADGROUP` with auto-claim of pending messages supports retry and multiple consumers since Redis 5.0. | Mature consumer-group rebalancing and offset management; superior at scale but adds client complexity. |
| **Exactly-once semantics** | At-least-once by default. **Exactly-once for billing** is implemented at the application layer: store processed `message-id` in PostgreSQL with a `UNIQUE` constraint, making the consumer idempotent. Billing events are low-volume, so this table stays small and hot. | Native exactly-once via idempotent producers and transactions; stronger primitive, but the application-level deduplication we need for Redis is straightforward and proven. |
| **Operational complexity** | **Low**: Redis is already deployed, monitored, and backed up. Adding Streams is a configuration change, not a new cluster. | **High**: ZooKeeper / KRaft, broker tuning, partition sizing, replication, and failure recovery require expertise we do not have in-house. |
| **Team ramp-up** | **Negligible**: senior engineers already operate Redis; mid-level engineers can read `XADD` / `XREADGROUP` documentation in hours. | **Weeks to months**: no Kafka experience on the team; two weeks is insufficient to deploy, tune, and safely migrate a billing-critical subsystem. |
| **Budget** | Uses existing Redis infrastructure; marginal cost is near zero. | Self-hosted Kafka on EC2 or MSK introduces new compute, storage, and monitoring costs. Managed Confluent Cloud is explicitly out of budget. |
| **WebSocket roadmap** | Redis Pub/Sub is the natural fit for real-time push; staying in the Redis ecosystem reduces future integration risk. | Would require a separate real-time layer (e.g., another Redis instance or WebSocket broker), adding architectural fragmentation. |

---

## Consequences

### Pros

1. **Fast time-to-value**: we can begin migrating notification types incrementally within days, not weeks.
2. **Operational safety**: existing runbooks, monitoring, and backup procedures apply immediately.
3. **Sufficient headroom**: 10× traffic growth (5,000 req/s) is still two orders of magnitude below Redis Streams throughput limits.
4. **Unified stack**: future WebSocket push can reuse Redis Pub/Sub, keeping the real-time and async infrastructure on one platform.
5. **Exactly-once is achievable**: PostgreSQL-backed idempotency for billing events is simple, durable, and verifiable.

### Cons

1. **Memory ceiling**: message retention is bounded by RAM. If message volume or consumer lag spikes unexpectedly, we risk evictions. We will mitigate this with active `XTRIM` policies, memory alerts, and an upper-bound stream length.
2. **Manual exactly-once**: unlike Kafka transactions, we must build and maintain the idempotency table ourselves. A bug in consumer ACK logic could re-deliver a billing email.
3. **Limited replayability**: trimming the stream discards history; long-term audit or replay requires archiving consumed messages to PostgreSQL or S3.
4. **Scaling friction beyond 10×**: if we outgrow a single Redis node, sharding streams across multiple Redis instances is manual. At that point we will likely revisit Kafka.
5. **Less ecosystem tooling**: lacks the mature stream-processing frameworks (e.g., Kafka Streams, ksqlDB) available in the Kafka ecosystem.

---

## Alternatives Considered

### Apache Kafka

Kafka was rejected because its strengths — extreme throughput, native exactly-once transactions, and deep stream-processing ecosystem — are mismatched to our current constraints. The team has no Kafka expertise and no infrastructure engineer to operate a self-hosted cluster. A two-week migration window is incompatible with safely deploying, tuning, and hardening Kafka for billing-critical traffic. Managed offerings exceed our modest budget. We will re-evaluate Kafka if traffic grows well beyond 10× or if we require complex stream processing (e.g., event sourcing across multiple domains).

---
