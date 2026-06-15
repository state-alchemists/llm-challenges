# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

## Context

Our SaaS project-management platform serves 85,000 monthly active users and creates ~2M tasks per month, with a peak load of ~500 req/s during business hours. Notifications (emails and webhooks) are currently processed synchronously inside the HTTP request cycle, causing:

- Average notification latency of 800ms, spiking to 8s under load.
- Silent failures with no retry mechanism when downstream providers are unavailable.
- Two incidents this year where a slow webhook endpoint caused connection-pool exhaustion and cascading outages.
- No delivery guarantees for billing-critical events (e.g., "trial expired", "payment failed"), which must be delivered exactly once.

We need to decouple notification delivery from the request cycle, introduce retry with exponential backoff, guarantee at-least-once delivery, achieve exactly-once semantics for billing events where feasible, and lay the groundwork for real-time WebSocket push within two quarters. The target is to support 10x traffic growth without re-architecting.

**Team constraints**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer. We already operate Redis (sessions and rate limiting) but have no Kafka experience. The migration must deliver value within two weeks, and the budget is modest—managed Confluent Cloud is not viable at full scale.

## Decision

**We will adopt Redis Streams as the notification backbone.**

This choice is driven by operational fit, team bandwidth, and the traffic profile, not by theoretical peak throughput. Redis Streams gives us the primitives we need—persistent ordered streams, consumer groups, and per-message acknowledgements—with a setup and operational burden the team can absorb today.

### Justification

| Property | Redis Streams Fit | Rationale |
|----------|-------------------|-----------|
| **Throughput** | Redis single-node throughput routinely exceeds 100k ops/sec. Our peak is 500 req/s; 10x growth lands at ~5k req/s, leaving 20× headroom. | More than sufficient for the scaling target without sharding complexity. |
| **Ordering guarantees** | Messages are strictly FIFO within a single stream. We can shard by `tenant_id` or `user_id` when stronger partition ordering is needed. | Preserves causality for per-user notification sequences (e.g., task assigned → task completed). |
| **Message retention** | `MAXLEN` or `MINID` trims keep memory bounded. Notifications are ephemeral (source of truth is PostgreSQL); a retention window of 3–7 days is adequate. | Disk-based retention (Kafka) is overkill for this use case and adds operational surface area. |
| **Consumer groups** | Native `XREADGROUP` with automatic assignment and the Pending Entries List (PEL). Failed consumers leave messages in PEL for automatic or explicit re-claiming by others. | Covers failover, back-pressure, and retry without external orchestration. |
| **Exactly-once semantics** | Redis Streams provides at-least-once delivery natively. Exactly-once for billing events will be implemented at the application layer: idempotent consumers keyed by stream entry ID, with deduplication state stored in PostgreSQL using an `INSERT ... ON CONFLICT DO NOTHING` pattern (or Redis `SETNX` for short-lived dedup windows). | Application-level idempotency is simpler to reason about and verify than Kafka’s producer/transaction/isolation-level configuration, especially for a team without Kafka experience. |
| **Operational complexity** | We already run Redis in production. Adding Streams is a configuration change, not a new system to deploy, monitor, backup, or tune. | Eliminates the risk of a multi-week Kafka deployment blocking value delivery. |
| **Strategic alignment** | Redis Pub/Sub is the natural technology for the WebSocket push layer planned in the next two quarters. Staying in the Redis ecosystem keeps the stack cohesive. | Reduces future integration and operational overhead. |

Given the two-week setup constraint and the absence of a dedicated infrastructure engineer, the risk of a misconfigured or poorly tuned self-hosted Kafka cluster—leading to exactly the kind of instability we are trying to escape—outweighs Kafka’s long-term scaling advantages.

## Consequences

### Pros

- **Rapid migration**: A working stream pipeline can be deployed in days using existing Redis infrastructure, keeping us well inside the two-week window.
- **Low operational surface area**: One less distributed system to monitor, upgrade, and troubleshoot. The team’s existing Redis expertise transfers directly.
- **Unified stack for future real-time features**: Redis Pub/Sub is the proven next step for WebSocket push; we avoid introducing a third messaging technology.
- **Sufficient scalability margin**: 5k req/s at 10× growth is comfortably within Redis’s operational envelope on modest AWS instances.
- **Predictable cost**: Near-zero incremental infrastructure cost; no managed-service premium or dedicated Kafka broker fleet.

### Cons

- **Exactly-once is an application concern**: We must build and audit idempotency logic for billing notifications. A bug in deduplication could produce duplicates, whereas Kafka offers stronger native exactly-once primitives (idempotent producer + transactions).
- **Memory-bound retention**: Retention is limited by RAM. If trimming is misconfigured or traffic spikes unexpectedly, older unconsumed messages could be evicted. We will mitigate this with `MAXLEN ~approx` trimming, aggressive alerting on memory usage, and a dead-letter/archival path to PostgreSQL for billing events.
- **Less mature stream-processing ecosystem**: There is no equivalent to Kafka Streams or Kafka Connect. Complex multi-stage stream joins or external system integrations will require custom Python workers.
- **High-availability gap**: Our current Redis setup must be hardened (Redis Sentinel or a small Cluster) to prevent the notification stream from becoming a single point of failure. This is required work regardless of the stream choice, but it is a prerequisite for production confidence.

## Alternatives Considered

### Apache Kafka

Kafka was evaluated and rejected for this stage of the platform.

- **Operational burden**: A production Kafka deployment (even KRaft mode) requires deep expertise in partition sizing, replication, ISR management, and consumer rebalancing. Our 6-person team has no Kafka experience and no dedicated infrastructure engineer to own it.
- **Setup timeline**: A reliable self-hosted cluster—including provisioning, tuning, monitoring, and failure-runbook creation—would exceed the two-week value-delivery window and likely slip into months.
- **Exactly-once complexity**: Kafka’s exactly-once semantics (idempotent producer + transactional writes + isolation-level tuning) are powerful but notoriously finicky to configure and verify. The risk of misconfiguration that silently degrades to at-least-once—or worse, loses messages—is unacceptably high for a team learning the system under production pressure.
- **Cost**: Managed Confluent Cloud is ruled out by budget. Self-hosted Kafka on modest hardware would run at lower reliability than our existing Redis, trading one set of incidents for another.
- **Acknowledgement**: If we eventually outgrow Redis Streams (e.g., sustained >50k messages/sec, complex stream joins, or multi-region replication), Kafka remains the natural migration target. We will instrument stream volume and consumer lag metrics so that a future re-evaluation is data-driven.
