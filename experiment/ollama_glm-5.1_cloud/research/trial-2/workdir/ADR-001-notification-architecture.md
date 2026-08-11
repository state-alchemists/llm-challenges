# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users with ~2M tasks created per month and peak traffic of ~500 req/s. Notifications (emails and webhooks triggered by task updates, assignments, and completions) are currently processed synchronously inside the HTTP request cycle. This has led to four recurring problems:

1. **Request timeouts.** Blocking on notification dispatch adds ~800 ms to average response latency, spiking to 8 s during peak hours.
2. **Silent failures.** When an email provider or webhook endpoint is down, notifications are dropped with no retry and no dead-letter queue.
3. **Cascading failures.** Two incidents this year saw slow webhook endpoints exhaust the PostgreSQL connection pool, taking down unrelated features.
4. **No delivery guarantees.** Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once, but the current system offers no such guarantee.

The scaling target requires: asynchronous processing, retry with exponential backoff, at-least-once delivery (exactly-once where feasible for billing), WebSocket push within two quarters, and the ability to handle 10× traffic growth without re-architecting.

**Constraints that shape this decision:**

- **Team:** 6 engineers (3 senior, 3 mid-level). No dedicated infrastructure engineer.
- **Existing stack:** Redis is already in production for sessions and rate limiting.
- **Kafka experience:** None on the current team.
- **Time-to-value:** Must deliver working async notification processing within 2 weeks.
- **Budget:** Modest — managed Confluent Cloud at full scale is not affordable today.
- **Correctness:** Billing notifications require exactly-once delivery semantics.

We evaluated two messaging technologies to decouple notification production from delivery: **Apache Kafka** and **Redis Streams**.

## Decision

We choose **Redis Streams** as the notification subsystem's message broker.

### Justification

| Factor | Redis Streams | Apache Kafka |
|--------|--------------|--------------|
| **Operational footprint** | Already running; no new infrastructure | New cluster (3+ brokers minimum), ZooKeeper/KRaft, monitoring stack |
| **Time to first value** | Days — add `XADD`/`XREADGROUP` to existing Redis | Weeks — cluster provisioning, topic design, operator training |
| **Team readiness** | Familiar; Redis already in use | Zero experience; steep learning curve |
| **Throughput (current + 10×)** | 100 k+ msgs/s per shard — 5,000 req/s is trivial | Millions of msgs/s — overkill for our scale |
| **Message ordering** | Per-stream sequential; sufficient for per-entity ordering (one stream per notification type) | Per-partition sequential; stronger global ordering with single-partition topics |
| **Consumer groups** | `XREADGROUP` + `XACK` + `XPENDING`/`XCLAIM` — full group semantics | Mature consumer groups with rebalancing, offset management |
| **Message retention** | Configurable `MAXLEN` or time-based trimming; in-memory but persistable via AOF/RDB | Disk-based, configurable retention by size or time; superior for long-term replay |
| **Exactly-once semantics** | At-least-once delivery; exactly-once achieved via application-level idempotency (dedup keys on consumer) | Kafka Transactions provide exactly-once within the Kafka pipeline; external side effects (email, webhook) still require application-level idempotency |
| **Operational complexity** | Low — one process to monitor, already on-call | High — broker cluster, partition management, rebalancing, rack awareness, TLS |
| **Budget impact** | Zero incremental infra cost | Self-hosted: significant ops cost; Managed: budget-exceeding |

**Key reasoning:**

1. **Time-to-value is decisive.** The 2-week constraint means we cannot afford the ramp-up Kafka requires. With Redis Streams, we use an already-running service and APIs the team can learn in a day. A Kafka rollout would consume the entire 2-week window on infrastructure alone before writing a single notification handler.

2. **Kafka's exactly-once does not eliminate application-level idempotency.** Kafka Transactions guarantee exactly-once within the Kafka-to-Kafka pipeline. Our final delivery targets — email providers, webhook endpoints — are external systems. Whether we use Kafka or Redis Streams, we must implement idempotent consumers (e.g., dedup keys stored in PostgreSQL) to prevent duplicate emails or double webhook calls. Redis Streams' at-least-once plus idempotent consumers achieves the same effective exactly-once outcome for billing notifications.

3. **Scale is well within Redis Streams' capability.** Our 10× target (5,000 req/s) is far below Redis Streams' practical ceiling. We are not in the millions-of-messages-per-second regime where Kafka's architecture provides a meaningful throughput advantage.

4. **Operational simplicity compounds over time.** A 6-person team with no dedicated infra engineer cannot afford the pager burden of a Kafka cluster. Redis is already on-call; adding Streams does not increase the operational surface.

## Consequences

### Pros

- **Fast delivery.** Working async notification pipeline within days, not weeks. Meets the 2-week constraint.
- **No new infrastructure.** Leverages existing Redis deployment — no additional servers, licensing, or monitoring tooling.
- **Simpler operations.** One fewer distributed system to operate, monitor, and troubleshoot at 3 AM.
- **Consumer groups with delivery tracking.** `XREADGROUP` gives us consumer-group semantics, `XPENDING`/`XCLAIM` gives us visibility into stuck messages, and `XACK` confirms successful processing. These are sufficient for retry and dead-letter logic.
- **Adequate scale.** Handles 10× traffic growth with headroom. We can revisit Kafka when we approach 50,000+ req/s or need multi-service event sourcing.
- **Idempotent consumer pattern.** Implementing dedup keys in PostgreSQL for billing notifications gives us effective exactly-once delivery, and this pattern is portable if we ever migrate to Kafka.

### Cons

- **Memory-bound retention.** Redis Streams hold messages in memory. With `MAXLEN` trimming and AOF persistence, we can retain enough history for retry and short-term replay, but we lose the long-term event-log replay that Kafka's disk-based retention provides. Mitigation: archive processed notifications to PostgreSQL for audit and replay.
- **No built-in dead-letter queue.** We must implement DLQ logic ourselves (e.g., move messages to a failed stream after N retries). This is straightforward but not free.
- **Weaker global ordering.** Ordering is per-stream only. If cross-type notification ordering matters (e.g., "task assigned" before "task completed" for the same task), we must route related events to the same stream or handle out-of-order delivery on the consumer side.
- **Rebalancing is manual.** Kafka automatically rebalances consumer groups on member changes. Redis Streams require `XCLAIM`-based recovery or a supervisor process. For 6 consumers, this is manageable but less elegant.
- **Future migration risk.** If the platform grows beyond Redis Streams' sweet spot (e.g., event sourcing, multi-service log compaction, massive fan-out), we will need to migrate to Kafka. The idempotent consumer pattern and stream-per-notification-type design make this migration incremental, but it is still a future cost.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard choice for high-throughput, durable event streaming with strong ordering and delivery guarantees. We rejected it for this decision because:

- **Operational cost exceeds our capacity.** Running a production Kafka cluster (minimum 3 brokers, ZooKeeper or KRaft, monitoring, TLS, partition management) requires dedicated infrastructure expertise that our 6-person team does not have.
- **2-week timeline is infeasible.** Provisioning, securing, and hardening a Kafka cluster, plus training the team, would consume the entire window before we write any notification logic.
- **Budget does not support managed Kafka.** Confluent Cloud or AWS MSK at our message volume would be a meaningful ongoing cost increase.
- **Exactly-once benefit is marginal for our use case.** Kafka's exactly-once semantics cover the internal Kafka pipeline. Our delivery endpoints (SendGrid, webhook consumers) are external. Duplicate external deliveries require application-level dedup regardless of broker choice. The pattern we need — idempotent consumers with dedup keys — is identical under both Kafka and Redis Streams.
- **Throughput is overspecified.** Our 10× target (5,000 req/s) is well within single-digit percentage of Redis Streams' capacity. Kafka's millions-of-messages-per-second design point does not justify its operational overhead at our scale.

Kafka remains the right choice if we later need: multi-service event sourcing with log compaction, cross-team data contracts, or throughput in the hundreds of thousands of messages per second. We can migrate incrementally if we reach that point.