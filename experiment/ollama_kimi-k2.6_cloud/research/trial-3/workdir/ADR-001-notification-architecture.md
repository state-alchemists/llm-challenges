# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform (85,000 MAU, ~2M tasks/month, peak ~500 req/s) currently sends email and webhook notifications synchronously inside the HTTP request cycle. This is causing four concrete problems:

1. **Request timeouts** — Average notification latency is 800ms, spiking to 8s during peak hours, degrading user experience.
2. **Silent failures** — If an email provider or webhook endpoint is down, the notification is dropped with no retry mechanism or dead-letter queue.
3. **Cascading failures** — Two incidents this year where a slow webhook endpoint caused connection pool exhaustion, taking down unrelated features.
4. **No delivery guarantees** — Billing-critical notifications (e.g., "trial expired", "payment failed") must be delivered exactly once, but the current system provides no such guarantee.

We must decouple notifications from the HTTP request cycle, introduce async processing with retry and backoff, and guarantee at-least-once delivery for all events and exactly-once semantics for billing notifications. Within two quarters we also need to add real-time WebSocket push notifications, and the solution must handle 10x traffic growth without re-architecting.

Our constraints are tight:

- Engineering team of 6 (3 senior, 3 mid-level) with **no dedicated infrastructure engineer**.
- We already run **Redis in production** for session storage and rate limiting.
- **No Kafka experience** on the team today.
- We have **no more than 2 weeks** for setup and migration work before delivering value.
- **Modest budget** — managed Confluent Cloud is not financially viable at our current scale.

## Decision

We will adopt **Redis Streams** as the backbone of the new notification subsystem.

**Justification:** Redis Streams provides the best balance of capability, operational simplicity, and time-to-value given our team size, existing infrastructure, and hard deadline. It supports the specific technical properties we require — consumer groups for scalable fan-out, explicit acknowledgement (`XACK`) for at-least-once processing, configurable retention via `MAXLEN`/`MAXAGE`, and sufficient throughput for our 10x growth target — while leveraging infrastructure we already operate. Kafka's superior raw throughput and exactly-once transaction semantics are outweighed by the operational burden it imposes on a team with no Kafka expertise and no dedicated infrastructure support.

## Consequences

### Positive

- **Rapid time-to-value** — Redis Streams can be introduced incrementally alongside our existing Redis deployment. A senior engineer can have a working consumer group and dead-letter pattern running in days, not weeks.
- **Low operational overhead** — We already monitor, back up, and tune Redis. Adding Streams introduces no new failure domain, no new deployment artifact, and no new operational runbook.
- **Sufficient throughput headroom** — Redis Streams can sustain tens of thousands of messages per second per node. Our peak is ~500 req/s today; even at 10x growth (5,000 req/s) we remain comfortably within single-node capacity.
- **Native consumer groups** — `XREADGROUP` supports multiple consumers sharing a stream, automatic message assignment, and pending-entry-list (PEL) tracking for failure recovery. This gives us the horizontal scaling pattern we need without external coordination.
- **Message retention control** — `XTRIM` with `MAXLEN` or `MAXAGE` lets us bound memory usage while keeping enough history for replay and debugging.
- **Path to real-time push** — Redis Pub/Sub and Streams are already used for WebSocket backends. Our planned real-time push feature in two quarters will integrate naturally with the same Redis infrastructure.

### Negative

- **Exactly-once requires application-level discipline** — Redis Streams provides at-least-once delivery via `XACK`. True exactly-once semantics for billing notifications depend on idempotent consumers and careful handling of the PEL. We must implement defensive deduplication (e.g., idempotency keys in PostgreSQL) to guard against double-processing during consumer crashes or network partitions.
- **Retention is memory-bound** — Unlike Kafka, which persists streams to disk with O(1) read performance regardless of age, Redis Streams is constrained by available RAM. Aggressive trimming or memory pressure could reduce our message history window.
- **Operational tooling is thinner** — Kafka ships with mature ecosystem tools (Kafka Connect, Kafka Streams, schema registry, MirrorMaker, deep JMX metrics). Redis Streams tooling is lighter; we will need to build our own monitoring dashboards and lag alerts around `XPENDING` and stream length metrics.
- **Harder long-term scaling** — If we grow beyond single-node Redis capacity, sharding Streams across multiple Redis instances is more complex than Kafka's native partition model. A future migration to Kafka remains a possibility if we outgrow Redis.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard event streaming platform. It offers superior throughput, log-based durability with configurable replication, mature consumer group rebalancing, and strong exactly-once semantics (EOS with idempotent producers and transactions). Its message retention is disk-based and effectively unlimited, and its ecosystem is far richer than Redis Streams.

**Why we rejected it:**

- **Operational complexity** — A production Kafka cluster requires ZooKeeper (or KRaft), broker tuning, partition planning, replica management, and careful monitoring of consumer lag and rebalancing storms. Operating this safely without a dedicated infrastructure engineer is a significant risk for a 6-person team.
- **Team experience gap** — No engineer on the team has deployed, tuned, or debugged Kafka in production. The learning curve is steep, and mistakes (e.g., misconfigured `acks`, unhandled rebalances, or consumer group partitions) translate directly into production incidents.
- **Time-to-value exceeds our deadline** — Conservative estimates place a production-ready self-hosted Kafka deployment, consumer client integration, and operational runbook at 3–4 weeks. Our constraint is 2 weeks.
- **Budget constraint** — Managed Kafka (Confluent Cloud, MSK) would eliminate operational burden but exceeds our modest budget at scale. Self-hosting is the only viable path, compounding the complexity concerns above.
- **Overkill for current and near-future scale** — Our peak throughput (~500 req/s, ~4.3M events/day) is well within Redis Streams' capabilities. Kafka's primary advantage is at volumes one to two orders of magnitude higher than ours.

We acknowledge that Kafka may become the right choice if we outgrow Redis Streams or hire dedicated infrastructure expertise. We will re-evaluate when sustained throughput exceeds 20,000 messages/sec or when message retention requirements exceed available memory by an order of magnitude.
