# ADR-001: Notification Subsystem — Async Queue Substrate

**Status:** Proposed

---

## Context

The Notifier module sends email and webhook notifications when tasks are updated, assigned, or completed. Today it runs synchronously inside the Flask request cycle, causing three concrete production problems:

1. **Request timeouts** — Average latency 800 ms, spikes to 8 s under peak load (500 req/s), because outbound SMTP and HTTP calls block the response.
2. **Silent failures** — A downed email provider or webhook endpoint drops the notification permanently. No retry, no dead-letter queue.
3. **Cascading failures** — Slow webhook endpoints exhaust the connection pool, taking down unrelated features (two incidents in the past year).

### Requirements

The solution must:

- **Decouple** notification delivery from the HTTP request cycle.
- **Support retry with exponential backoff** and a dead-letter mechanism.
- **Guarantee at-least-once delivery** for billing-critical notifications (trial expiry, payment failure), with exactly-once semantics where practically achievable.
- **Accommodate WebSocket push** within two quarters.
- **Handle 10× current traffic** without a re-architecture.
- **Deliver value within two weeks** of starting the migration.
- **Stay within modest budget** — no managed Confluent Cloud.

### Team Constraints

- **6 engineers** (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **No Kafka experience** on the team.
- **Redis already in production** for session storage and rate limiting — the team knows it well.

---

## Decision

**Use Redis Streams** as the notification queue substrate.

Redis Streams will serve as the asynchronous buffer between the Flask request handlers and a pool of background workers that dispatch emails and webhooks. Worker processes will consume messages via consumer groups, acknowledge completed work with `XACK`, and manage retries with `XCLAIM` and a dead-letter stream.

We will augment this with an **idempotency-key pattern** (a deduplication table in PostgreSQL keyed on `(notification_id, event_id)`) to achieve exactly-once semantics for billing-critical notifications.

---

## Consequences

### Advantages

1. **Zero new infrastructure.** Redis already runs in production. Adding Streams requires no new servers, no new state stores, no new monitoring surface. The operational risk of standing up a new distributed system is eliminated entirely.

2. **Team familiarity.** Every engineer on the team has worked with Redis. The Streams API (XADD, XREADGROUP, XACK, XCLAIM) is learnable in hours. There is no multi-week ramp-up period.

3. **Rapid time-to-value.** A working notification worker consuming from a Redis Stream can be written, tested, and deployed within a week. This meets the two-week constraint with margin.

4. **Sufficient throughput.** A single Redis instance handles 100k+ operations per second on modest hardware. Our current peak is 500 req/s. At 10× growth (5k req/s), with each request producing ~2–3 notifications, the throughput is still an order of magnitude below Redis's ceiling. Throughput is not a binding constraint.

5. **Consumer groups provide at-least-once delivery.** The consumer group primitive (`XREADGROUP` + `XACK`) ensures each message is delivered to exactly one consumer in a group. If a consumer crashes without acknowledging, the message becomes pending and can be claimed by another consumer via `XCLAIM`. This directly solves the silent-failure problem.

6. **Retry and dead-letter is straightforward.** A worker that fails to deliver can `XCLAIM` the message into a retry stream (or back into the main stream with a delivery-count header). After N attempts, it moves to a dead-letter stream for manual inspection. No framework or external library required.

7. **WebSocket integration is natural.** Redis Pub/Sub can forward notification events to a WebSocket server alongside the stream-based delivery, giving us real-time push without adding another message broker.

8. **Memory is not a problem at this scale.** With `MAXLEN ~100k` and each message ~1 KB, the working set is ~100 MB. Notifications are consumed and acknowledged within seconds to minutes. The stream acts as a transient buffer, not a long-term log. Retention beyond that lives in PostgreSQL (the notification history table already exists).

### Disadvantages

1. **No true exactly-once to external systems.** Redis Streams guarantees at-least-once delivery within the consumer group. If a worker crashes after sending the email but before `XACK`, the notification is re-delivered. This is a property of all async messaging systems — Kafka's "exactly-once semantics" (EOS) does not solve this either, because it cannot roll back an external HTTP call. The real solution is consumer-side idempotency, which we implement regardless of the transport choice.

2. **Memory-bound retention.** Redis Stores data in RAM. Unlike Kafka (which writes to disk with a configurable retention period), Redis cannot retain a multi-day message log for replay without either keeping it in memory or writing an external archiver. For this use case — ephemeral notifications consumed within minutes — the constraint is irrelevant, but it rules out Redis Streams for use cases like audit-log replay or long-lived event sourcing.

3. **Manual partitioning at scale.** If a single stream becomes a bottleneck (unlikely before 50k+ notif/s), partitioning requires application-level logic: multiple stream keys, a routing strategy, and consumer affinity. Kafka handles partitioning natively. This is not a concern at our projected scale, but it is a genuine limitation if growth exceeds predictions by another order of magnitude.

4. **No built-in offset management across schema changes.** Kafka stores schema versions alongside messages (with Schema Registry). Redis Streams has no schema enforcement. If the notification payload format changes, old messages in-flight must be handled by the consumer code. This is manageable with a `version` field in the payload but requires discipline.

---

## Alternatives Considered

### Apache Kafka (Self-Hosted)

**Why rejected:** Operational complexity outweighs the benefits at this scale for this team.

Kafka is a superb event-streaming platform, but it is built for a different class of problem than ours:

- **Throughput mismatch.** Kafka's sweet spot begins in the tens of thousands of messages per second. Our peak of ~1,500 notifications/s (present) and ~15,000/s (10×) is well within Redis Streams' capability. Kafka's throughput advantage is irrelevant here.

- **Operational burden is real.** A production Kafka deployment (even without Confluent Cloud) requires: ZooKeeper or KRaft quorum management, broker JVM heap tuning, partition rebalancing, ISR health monitoring, and disk sizing for the retention period. For a 6-person team with no dedicated infrastructure engineer, this is a significant ongoing tax. Kafka's operational maturity is excellent — but it requires attention that Redis does not.

- **Learning curve.** The team has zero Kafka experience. Concepts like topics, partitions, consumer groups, offsets, ISRs, and exactly-once semantics have a real learning cost. A misconfigured consumer (e.g., auto-commit offset before processing) can silently lose messages. Redis Streams have a gentler slope and a smaller surface area.

- **Two-week timeline is infeasible.** Standing up a production Kafka cluster, integrating it with a Python consumer, setting up monitoring (JMX exporters, broker metrics, Lag), and validating the notification workflow would take 3–4 weeks for a team learning Kafka from scratch. The constraint is explicit: value within two weeks.

- **Self-hosted Kafka is not free.** While open-source Kafka has no license cost, the infrastructure is non-trivial: 3 brokers minimum, dedicated ZooKeeper/KRaft nodes, sufficient disk for retention, and the engineering time to maintain it. At our scale, Redis Streams runs on the existing instance with negligible additional cost.

- **Managed Kafka is too expensive.** Confluent Cloud pricing for a 3-broker cluster with moderate throughput starts around $1k–$2k/month. For our budget-constrained team, this is hard to justify when the existing Redis instance handles the load with zero additional spend.

**When we would reconsider Kafka:** If the notification system evolves into a full event-sourcing platform requiring multi-year log retention, replay across dozens of consumer groups, and integration with stream-processing frameworks (KSQL, Flink), or if throughput exceeds 100k msgs/s. None of these conditions apply today or in the foreseeable 2-year horizon.

---

## On Exactly-Once Semantics

A brief note because this requirement frequently drives architectural decisions more expensive than necessary.

True exactly-once delivery to an **external system** (email provider, webhook endpoint) is impossible with any async messaging substrate unless the consumer is idempotent. Both Kafka and Redis Streams face the same fundamental problem: a crash between "send HTTP request" and "acknowledge message" causes redelivery, and the transport cannot distinguish a timeout from a failure.

Our approach for billing notifications is:

1. **At-least-once delivery** from the queue (consumer group + XACK).
2. **Idempotent consumers** that check a deduplication table (`notification_outbox_events`) keyed on `(notification_id, event_id)` before performing the side effect. A PostgreSQL unique constraint enforces the invariant.
3. **Outbox pattern** on the producer side: write the notification event and the stream `XADD` inside the same PostgreSQL transaction using a transactional outbox + a relay process (or, for simplicity during the first phase, write to the stream directly with a fallback cleanup task).

This gives us the practical equivalent of exactly-once for billing notifications without depending on any transport-level EOS feature.

---

*Decision date: 2026-06-23*
