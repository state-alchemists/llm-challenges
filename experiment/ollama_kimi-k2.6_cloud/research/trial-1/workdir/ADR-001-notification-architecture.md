# ADR-001 — Notification Subsystem Architecture

## Status

Proposed

---

## Context

Our SaaS project-management platform currently sends notifications (email and webhooks) synchronously inside the HTTP request cycle. At peak load (~500 req/s) this produces:

- Average notification latency of 800 ms, spiking to 8 s.
- Silent drops when downstream providers fail, with no retry or dead-letter mechanism.
- Two cascading-failure incidents this year caused by slow webhook endpoints exhausting connection pools.
- No delivery guarantee for billing-critical events ("trial expired", "payment failed").

We must decouple notification dispatch from request handling, introduce retries with exponential backoff, and provide at-least-once delivery for general notifications and exactly-once semantics for billing events. Within two quarters we also intend to add real-time WebSocket push.

Team context shapes the choice:

- Six engineers (three senior, three mid-level), **no dedicated infrastructure engineer**.
- Redis is already in production for session storage and rate-limiting.
- **No operational experience with Kafka**.
- Budget is modest; managed Kafka (Confluent Cloud, MSK) is not viable at our scale today.
- Migration must deliver value within **two weeks**.

---

## Decision

> We will use **Redis Streams** as the backing message bus for the notification subsystem.

The notification layer will publish events to typed streams (`notifications:email`, `notifications:webhook`, `notifications:billing`). Workers will consume these streams via Redis consumer groups, using PostgreSQL as an idempotency store for billing events to achieve exactly-once semantics.

Redis Streams was chosen because it satisfies our functional requirements while respecting our hardest constraints: team bandwidth, operational headroom, and time-to-value.

### Justification

1. **Operational fit.** We already run Redis in production. Adding Streams uses existing infrastructure rather than introducing a new broker that no one on the team has operated. With no dedicated SRE, operational simplicity is a first-class requirement, not a nice-to-have.

2. **Time-to-value.** Redis Streams can be enabled on our existing Redis instance (or a small secondary instance for isolation) in hours. A team with no Kafka experience cannot safely deploy, tune, and harden a self-managed Kafka cluster—complete with KRaft/ZooKeeper, broker sizing, partition planning, and monitoring—in two weeks without unacceptable risk.

3. **Throughput adequacy.** Our current peak is ~500 req/s. Even 10× growth (5 000 req/s) is well within the sustained throughput of a single Redis node on modern hardware (hundreds of thousands of ops/sec). We do not need Kafka’s partition-scaled throughput today, and we cannot afford the operational tax it levies at our scale.

4. **Ordering and consumer-group semantics.** Redis Streams provides per-stream ordering, consumer-group tracking, and automatic pending-message management (`XPENDING`, `XCLAIM`). These map directly to the fan-out and retry patterns we need for email and webhook workers.

5. **Path to real-time WebSockets.** Our planned WebSocket push layer will use Redis Pub/Sub. Co-locating the stream and pub/sub layers in the same technology reduces infrastructure sprawl and lets us reuse operational playbooks.

6. **Exactly-once for billing events.** Kafka offers native idempotent producers and transactions, but achieving true exactly-once still requires consumer-side deduplication. Redis Streams lacks built-in producer idempotency, so we will implement idempotency explicitly: billing workers upsert a `processed_message_id` record in PostgreSQL (with a unique index on `message_id`) before executing the notification side-effect. This is a well-understood pattern, adds minimal latency, and is safer than attempting to operate an unfamiliar distributed transaction coordinator under a two-week deadline.

---

## Consequences

### Positive

- **Faster migration.** Existing Redis expertise and infrastructure mean we can ship async notifications in days, not weeks.
- **Lower operational burden.** One fewer technology to monitor, patch, and troubleshoot; existing Redis dashboards and alerts apply.
- **Cost avoidance.** No additional licensing or managed-service fees. A secondary Redis instance for stream isolation is inexpensive compared to a Kafka cluster or managed offering.
- **Unified real-time stack.** Future WebSocket work reuses the same datastore and client libraries.
- **Simpler failure modes.** Redis has fewer moving parts than a Kafka cluster; recovery from node failure or restart is straightforward with AOF/RDB persistence.

### Negative

- **Exactly-once is application-layer concern.** Billing consumers must manage idempotency keys in PostgreSQL. A misconfiguration or missing check could allow duplicate delivery.
- **Retention is memory-bound.** Messages are retained by maxlen or TTL. We must configure capped streams (`MAXLEN ~`) or periodic trimming to prevent unbounded memory growth. Long-term archival for audit purposes may require an external sink.
- **Scaling ceiling.** If we grow beyond roughly 10–20× current throughput, a single Redis node (even with replicas) may become a bottleneck, forcing a move to Redis Cluster or a dedicated streaming platform. That threshold is estimated, not measured.
- **Consumer-group rebalancing is manual.** Redis does not automatically rebalance consumers across nodes; adding or removing worker processes requires careful `XGROUP` management.
- **Durability trade-off.** Redis persistence (AOF) is configurable but not as rigorously audited for crash safety as Kafka’s replicated log. We accept this by running Redis with `appendfsync everysec` and monitoring replication lag.

---

## Alternatives Considered

### Apache Kafka

**Why rejected.**

Kafka is architecturally superior for high-throughput, log-durable streaming and offers stronger exactly-once primitives (idempotent producers + transactions). However, it was rejected for the following reasons:

- **Operational gap.** The team has zero operational experience with Kafka. Safely deploying a production-grade cluster—including broker tuning, topic/partition design, consumer-group offset management, and failure recovery—would consume far more than two weeks and carries high risk without an infrastructure specialist.
- **Cost constraint.** Managed Kafka (Confluent Cloud, Amazon MSK) was ruled out by budget. Self-hosted avoids licensing costs but imposes the hidden cost of engineering time spent on operations rather than product features.
- **Overkill for current scale.** Kafka’s horizontal partitioning shines at tens or hundreds of thousands of messages per second. Our 500 req/s peak does not justify the added complexity.
- **Exactly-once is not free.** Even with Kafka, consumers must be idempotent or transactional. The delta between Kafka’s native support and an explicit deduplication table in PostgreSQL is small at our throughput and adds disproportionately more operational risk.

Kafka would become the right choice if our throughput crosses ~50 000 messages/sec, if we acquire dedicated infrastructure expertise, or if our budget allows a managed offering that abstracts away operational complexity.
