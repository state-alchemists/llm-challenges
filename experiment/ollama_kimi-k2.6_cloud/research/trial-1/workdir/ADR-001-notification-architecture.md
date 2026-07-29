# ADR-001: Notification Subsystem Architecture

## Status

**Proposed**

## Context

The Notifier subsystem in our SaaS project management platform currently sends emails and webhooks synchronously inside the HTTP request cycle. This has caused:

- **Request timeouts**: Average 800ms latency, spiking to 8s during peak hours (~500 req/s).
- **Silent failures**: No retry or dead-letter queue when providers or webhook endpoints are down.
- **Cascading failures**: Slow webhook endpoints have caused connection pool exhaustion, taking down unrelated features.
- **No delivery guarantees**: Billing-critical notifications (trial expiry, payment failure) lack exactly-once delivery guarantees.

We must decouple notification generation from delivery, add retry with exponential backoff, guarantee at-least-once delivery for all events, and achieve exactly-once semantics for billing-critical notifications. Within two quarters we also need to add real-time WebSocket push notifications. The target is to support 10x traffic growth (~5,000 req/s peak) without re-architecting.

**Team & infrastructure constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- We already operate Redis (AWS ElastiCache) for sessions and rate limiting.
- No Kafka experience on the team today.
- Setup and migration must deliver value within **2 weeks**.
- Budget is modest; managed Confluent Cloud or MSK at scale is not affordable today.

## Decision

**We will adopt Redis Streams as the notification messaging backbone.**

Redis Streams is the correct trade-off for our team size, existing infrastructure, time constraints, and throughput requirements. We will implement exactly-once semantics for billing notifications at the **application layer** using idempotency keys tracked in PostgreSQL, rather than relying on broker-level transactions.

### Justification

| Property | Redis Streams | Relevance to our constraints |
|---|---|---|
| **Throughput** | ~100k–500k messages/sec per node (memory-bound). At our peak of 500 req/s and 10x target of 5,000 req/s, a single Redis primary has ample headroom. | Sufficient for our growth target without clustering. |
| **Ordering guarantees** | Strict total ordering per stream key. Messages are monotonically increasing by ID. | Guarantees billing events are processed in sequence. |
| **Message retention** | Configured via `MAXLEN` or time-based trimming (`MINID`). Unacknowledged messages remain in the pending list indefinitely until `XACK` or `XCLAIM`. | Supports replay and recovery; we will cap streams to prevent unbounded memory growth. |
| **Consumer groups** | Native support (`XREADGROUP`, `XACK`, `XCLAIM`, `XPENDING`). Automatic rebalancing across consumers. | Enables horizontal scaling of worker pods without custom coordination code. |
| **Exactly-once semantics** | Redis Streams provides **at-least-once** delivery. We will supplement this with idempotent consumers: each notification carries a UUID; the worker checks a `processed_notifications` table in PostgreSQL before delivery. | Achieves effectively exactly-once for billing events without the complexity of Kafka transactions. |
| **Operational complexity** | We already run Redis in production. Redis Streams uses the same protocol, monitoring, and failover logic (ElastiCache Multi-AZ) we operate today. | Fits within our 2-week migration window and eliminates the need for new runbooks or hiring. |
| **Real-time (WebSocket) path** | Redis Pub/Sub can be layered alongside Streams for sub-millisecond WebSocket fanout, reusing the same Redis cluster. | Satisfies the 2-quarter WebSocket objective without introducing a third messaging system. |

Kafka offers superior raw throughput, longer retention on cheap disk, and native exactly-once producer transactions. However, for a 6-person team with no Kafka expertise and no dedicated SRE, self-hosting Kafka (or even a minimal KRaft cluster) within 2 weeks while simultaneously building consumer logic and idempotency patterns introduces unacceptable operational risk. Managed Kafka is ruled out by budget.

## Consequences

### Pros
- **Fast migration**: We can begin queuing notifications to a Redis Stream in a matter of days because our Python stack already uses `redis-py`.
- **Low operational surface area**: One less infrastructure component to monitor, back up, and upgrade. Our existing ElastiCache alarms and failover automation cover the new use case.
- **Consumer-group resilience**: `XCLAIM` and `XPENDING` give us dead-letter and retry semantics natively without additional middleware.
- **Future WebSocket convergence**: The same Redis cluster can later serve Pub/Sub for real-time push, avoiding a polyglot messaging estate.
- **Cost**: No new infrastructure spend; Streams runs on our existing cache nodes.

### Cons
- **Memory-bound retention**: Redis Streams live in RAM. Aggressive trimming or large backlogs risk data loss if workers are down for extended periods. We must enforce `MAXLEN` policies and monitor memory closely.
- **At-least-once default**: Exactly-once is an application-layer concern. If the idempotency table is misimplemented or a race condition occurs, a billing email could be duplicated. We must invest in robust deduplication logic and cover it with tests.
- **Weaker cross-stream ordering**: Ordering is strict within a single stream key, but not across multiple keys. If we partition billing events into multiple streams, total ordering is lost unless we use a single key or implement sequencing in the application.
- **Operational ceiling**: If we grow beyond ~10,000 sustained req/s or need months of retention, we will likely outgrow a single Redis primary and must either shard or re-evaluate Kafka. We accept this risk because it is years away at current growth rates.

## Alternatives Considered

### Apache Kafka (rejected)

Kafka was evaluated because it offers durable disk-based retention, massive horizontal throughput, and native exactly-once semantics via idempotent producers and transactions.

**Why rejected:**
- **Operational complexity**: A production Kafka deployment (even KRaft mode) requires broker tuning, partition balancing, and careful monitoring. Our team lacks the expertise and headcount to own this safely.
- **Time to value**: We estimated 2–4 weeks just to reach a stable, monitored Kafka cluster and rewrite producers/consumers, exceeding our 2-week mandate.
- **Cost**: Managed options (Confluent Cloud, MSK) are disproportionately expensive for our modest budget. Self-hosted shifts operational burden onto engineers who should be building product.
- **Overkill for scale**: At 500 req/s peak with a 10x target of 5,000 req/s, Kafka’s throughput advantage is irrelevant. Redis Streams can absorb this volume on a single node.
- **Exactly-once overhead**: Kafka transactions add latency and complexity (transactional IDs, `commitTransaction`, consumer isolation levels). For a team new to Kafka, the risk of misconfiguration leading to stalled consumers or zombie instances outweighs the theoretical correctness benefit.

We will revisit Kafka only if we exceed Redis’s vertical scaling limit or need multi-month message retention with tiered storage.
