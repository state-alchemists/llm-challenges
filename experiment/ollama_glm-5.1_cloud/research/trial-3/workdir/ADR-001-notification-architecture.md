# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails and webhooks triggered by task updates, assignments, and completions — **synchronously inside the HTTP request cycle**. This causes:

1. **Request timeouts**: Average notification latency is 800ms, spiking to 8s at peak.
2. **Silent failures**: No retry or dead-letter queue when providers are down.
3. **Cascading failures**: Slow webhook endpoints have exhausted the connection pool twice this year, taking down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications (trial expiry, payment failure) require exactly-once delivery but have none.

We must decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing where feasible), and support real-time WebSocket push within two quarters — all while absorbing 10x traffic growth.

**Constraints:**
- 6-person team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already in production (sessions, rate limiting)
- No Kafka experience on the team
- Maximum 2 weeks of setup/migration before delivering value
- Modest budget — managed Confluent Cloud at full scale is not affordable today
- Exactly-once semantics required for billing notifications

## Decision

**Choose Redis Streams** as the message broker for the notification subsystem.

Justification:

**Operational fit.** We already operate Redis in production and the team has deep familiarity with it. Introducing Kafka means operating a new distributed system — ZooKeeper/KRaft, brokers, topic management, monitoring — with no in-house experience and no dedicated infra engineer. For a 6-person team, that operational surface area is a material risk to reliability.

**Time-to-value.** Redis Streams can be integrated into the existing Flask monolith within the 2-week constraint: add `XADD` calls where notifications are currently sent synchronously, write a consumer process using `XREADGROUP`, and add `XACK` + retry logic. Kafka would require cluster provisioning, security configuration, client library adoption, and operator training before the first notification is dequeued — realistically 4–6 weeks before value.

**Throughput is sufficient.** Our peak is 500 req/s; 10x growth puts us at 5,000 msg/s. A single Redis instance handles 100k+ ops/s on modest hardware. Redis Streams comfortably covers our scaling target with headroom.

**Exactly-once for billing is achievable.** Kafka offers transactional exactly-once semantics at the broker level, but realizing them in Python requires correct use of the transactional producer API, idempotent consumers, and careful offset management — a pattern the team has no experience with and that is easy to get wrong. With Redis Streams, we implement effectively-once delivery for billing notifications via **application-level idempotency**: each billing notification carries a deterministic ID; the consumer checks a delivery log in PostgreSQL before sending, preventing duplicates even under redelivery. This is the same deduplication layer you'd need alongside Kafka's exactly-once guarantees in practice (Kafka's exactly-once prevents duplicate consumption, but the external side effect — sending an email — still requires idempotency at the provider call). Redis Streams gives us at-least-once delivery (`XACK` + pending-entry-list for retry); the application deduplication layer closes the gap to exactly-once.

**Cost.** Self-hosted Kafka on AWS requires 3+ broker nodes plus ZooKeeper/KRaft nodes for production-grade fault tolerance. Redis is already paid for and running.

## Consequences

### Pros

- **Fast delivery.** Notification async processing can ship within the 2-week window, immediately eliminating request-cycle blocking, timeouts, and cascading failures.
- **Low operational overhead.** No new distributed system to run, monitor, or upgrade. The team already operates Redis.
- **Sufficient performance.** Redis Streams handles 5,000 msg/s (our 10x target) with wide margins. Consumer groups (`XREADGROUP`) provide the partitioned consumption model we need for parallel workers.
- **At-least-once delivery.** `XACK` + pending-entry-list gives confirmed delivery with automatic re-delivery of unacknowledged messages — a direct fix for today's silent failures.
- **Dead-letter handling.** After N retries, messages move to a DLQ stream for manual inspection — resolving the current gap where failures are silently dropped.
- **WebSocket readiness.** Redis Pub/Sub or Streams can fan out to WebSocket servers in the next phase, without introducing a second messaging system.
- **Cost efficiency.** No additional infrastructure spend beyond the existing Redis instance (which may need a memory resize, far cheaper than a Kafka cluster).

### Cons

- **No broker-level exactly-once.** Redis Streams provides at-least-once; exactly-once for billing notifications depends on application-level idempotency (deduplication table). This works but requires discipline — every billing consumer must check the dedup log before acting. If the team skips this step, duplicate notifications result.
- **Memory-bound retention.** Redis Streams hold messages in memory (with optional disk persistence via RDB/AOF). Under 10x growth with high notification volume, we must monitor memory and tune `MAXLEN` or `XTRIM` to cap stream length. Unlike Kafka's configurable disk-based retention, older messages are pruned, not archived. For notifications (ephemeral by nature), this is acceptable, but it means we cannot replay the full history beyond the retention window.
- **Consumer group maturity.** Redis Streams consumer groups are functional but less battle-tested than Kafka's. There is no built-in rebalancing on consumer failure — our supervisor must handle worker restarts and claim pending messages via `XPENDING`/`XCLAIM`. This is straightforward to implement but is code we maintain rather than a feature we get from the broker.
- **Single-node risk.** Our current Redis is not clustered. If it goes down, notification processing halts. Mitigation: Redis Sentinel or a replica for automatic failover — still simpler than operating a Kafka cluster, but a step we must take before production reliance.
- **Future migration possible.** If we eventually exceed Redis Streams' capabilities (e.g., event sourcing with long-lived event logs, multi-service choreography), we would need to migrate to Kafka. The async producer/consumer interfaces we build can be abstracted behind an internal API, making this migration tractable, but it is still a non-zero cost.

## Alternatives Considered

### Apache Kafka

Kafka is the stronger choice for systems requiring durable, long-retention event logs, massive throughput, and broker-level exactly-once semantics across many independent consumer groups. If we were building an event-driven microservices platform with dozens of services, Kafka would be the right foundation.

**Why rejected for this decision:**

- **Operational complexity exceeds team capacity.** Running Kafka in production (even with KRaft removing the ZooKeeper dependency) requires expertise in broker sizing, partition strategy, compaction, replication factor tuning, and monitoring. We have no Kafka experience and no dedicated infrastructure engineer. A misconfigured Kafka cluster is worse than no Kafka — it creates a fragile dependency that the team cannot debug under pressure.
- **2-week constraint is infeasible.** Provisioning, hardening, and integrating a Kafka cluster, plus training the team, will take 4–6 weeks minimum. The notification problem is urgent — we have had two production incidents from the current architecture this year.
- **Exactly-once advantage is narrower than it appears.** Kafka's transactional exactly-once semantics prevent duplicate consumption of records. But our delivery side effect (sending an email via an external provider) is inherently non-transactional. Even with Kafka, we need the same application-level idempotency layer for billing notifications. The broker-level guarantee reduces but does not eliminate the deduplication requirement for external side effects.
- **Cost.** Self-hosted Kafka on AWS requires a minimum of 3 broker nodes (t3.medium or better) plus operational overhead. Managed Confluent Cloud starts at a price point that exceeds our budget at the traffic volumes we project. Redis is already running and paid for.
- **Kafka would be the right choice if**: the team had Kafka experience, we had a dedicated infra engineer, the timeline were 2+ months, or we needed multi-topic event streaming beyond notifications. None of these hold today. We should revisit Kafka if the notification subsystem evolves into a broader event backbone serving multiple consumer teams.