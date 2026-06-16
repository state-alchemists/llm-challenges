# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

## Context

The SaaS project management platform sends email and webhook notifications on task updates, assignments, and completions. At 85,000 MAU creating ~2M tasks/month, the current synchronous in-process notification model has broken down:

- **Request timeouts** — average 800ms latency, spiking to 8s during peak 500 req/s load.
- **Silent failures** — email provider or webhook outages drop notifications with no retry or dead-letter queue.
- **Cascading failures** — two incidents this year where a slow webhook endpoint exhausted the PostgreSQL connection pool, taking down unrelated features.
- **No delivery guarantees** — billing-critical notifications (trial expiry, payment failures) have no exactly-once or at-least-once guarantee.

We need an async notification pipeline that decouples delivery from the HTTP request cycle, supports retry with exponential backoff, guarantees at-least-once delivery (with exactly-once for billing events), and can be extended to real-time WebSocket push within two quarters. The system must handle 10x traffic growth without re-architecting.

**Constraints:**

| Constraint | Impact |
|---|---|
| Team: 6 people, no dedicated infrastructure engineer | Operational complexity must be low |
| Redis already in production (session storage, rate limiting) | Existing infrastructure available |
| Zero Kafka experience on the team | Learning curve is a real cost |
| Must ship value within 2 weeks | Setup and migration time is capped |
| Modest budget — no managed Confluent Cloud at full scale | Must self-host or use existing infrastructure |
| Exactly-once semantics required for billing notifications | Architecture must support idempotent delivery |

## Decision

**Use Redis Streams.**

Redis Streams will serve as the notification message bus. Producers (the Flask monolith) write notification events to streams partitioned by notification type (email, webhook, billing). Consumer processes read from consumer groups, handle delivery, and acknowledge messages on success. Failed deliveries are re-queued into a retry stream with exponential backoff; messages exceeding the retry limit land in a dead-letter stream for manual inspection.

### Justification

Three facts make this the right call:

**1. Existing Redis eliminates operational risk and time-to-value.**

We already run Redis for session storage and rate limiting. Adding Redis Streams means zero new infrastructure — no new brokers, no new state machines to monitor, no new backup procedures. A senior engineer familiar with our Redis setup can have a working producer-consumer pipeline in a day. This meets the 2-week delivery constraint comfortably.

Compare: standing up Kafka from scratch requires provisioning brokers, configuring KRaft or ZooKeeper, sizing disks for retention, setting up monitoring, and learning a new client protocol. On a 6-person team without Kafka experience, that alone consumes the 2-week budget before writing any application code.

**2. Throughput requirements do not justify Kafka's complexity.**

At 500 req/s peak and ~2M tasks/month, notification volume is well under 100 messages/second — even after factoring in expansion to WebSocket push. Redis Streams handle 100k+ operations/second on modest hardware. Kafka's million-messages-per-second throughput is an unused capability that we would pay for in operational cost and team attention.

For 10x growth (50M tasks/month, ~5k req/s peak), Redis Streams still comfortably fit within a properly configured Redis instance. At 100x growth we might revisit, but that is years away and the migration path (Redis Streams → Kafka) is straightforward — both use the same consumer-group abstraction and streaming semantics.

**3. Exactly-once is a consumer-side problem, not a transport problem.**

True exactly-once delivery to an external endpoint (SMTP server, HTTP webhook) is impossible at the transport layer. Even Kafka's transactional exactly-once semantics apply only within the producer → broker → consumer boundary. The moment a consumer makes an external HTTP call and the response is lost to a network partition, the message status is ambiguous.

The correct pattern for billing notifications — and it works identically on Redis Streams and Kafka — is:

1. Assign each notification a unique idempotency key (UUID).
2. The consumer checks the idempotency store (PostgreSQL or Redis) before delivery.
3. On success, record completion in the store. On failure or timeout, do not record — the message will be redelivered.
4. Use `XACK` (Redis) or manual offset commit (Kafka) after the idempotency record is committed.

This gives exactly-once semantics at the application level regardless of which transport sits underneath. Redis Streams' `XREADGROUP` with consumer group tracking provides the necessary at-least-once foundation.

## Consequences

### Positive

- **Fast time-to-value.** A working async notification pipeline can be shipping within a week. The 2-week constraint is conservative.
- **Zero new infrastructure.** No new AWS services, no new stateful instances to patch or monitor. The existing Redis cluster absorbs the load with trivial capacity headroom.
- **Team-aligned complexity.** Every engineer on the team already understands Redis data structures and operational patterns. `XADD`, `XREADGROUP`, `XACK`, and `XPENDING` are learnable in an afternoon.
- **Consumer groups for WebSocket push.** Redis Streams' consumer group model maps directly to distributing real-time events across WebSocket server instances — exactly the architecture needed for the 2-quarter WebSocket roadmap.
- **Pub/sub bridge available.** For truly ephemeral real-time events (typing indicators, presence), Redis Pub/Sub can complement the stream-based durable pipeline without introducing another dependency.
- **No throughput ceiling at projected scale.** Redis Streams on our existing infrastructure handles 10x current load without tuning.
- **Self-contained retry + DLQ.** Retry streams with `XEXPIRETIME` (Redis 7.4+) or maxlen-based expiration keep the retry pipeline bounded. Dead-letter queues are simply additional streams consumers can monitor.

### Negative

- **Memory-bound retention.** Stream messages live in memory until capped by `MAXLEN` or evicted. For our workload (notifications are consumed and acknowledged within seconds), this is acceptable — messages are not a source of truth. Task state lives in PostgreSQL; notifications are derived events. Configure `MAXLEN ~ 100000` per stream to bound memory usage.
- **No built-in replay to arbitrary point.** Redis Streams support reading from any message ID (`XRANGE`), but there is no Kafka-style offset management for time-based replay. Mitigation: for forensic replay, log notification IDs to PostgreSQL; for operational replay, the consumer group's `XPENDING` list captures unacknowledged messages.
- **Less ecosystem tooling.** Kafka has Kafka Connect, Schema Registry, KSQL, and deeper monitoring integrations. Redis Streams has less out-of-the-box ecosystem support. Mitigation: our pipeline is simple — Flask produces, Python consumers deliver. We do not need Kafka Connect or KSQL. Monitoring via `INFO streams` and `XLEN` is sufficient at our scale.
- **Smaller community and less operational lore.** Redis Streams are newer than Kafka. Fewer blog posts about production pitfalls. Mitigation: the patterns are well-documented in Redis documentation and Antirez's original design posts. Redis Ltd. now actively maintains and promotes streams.

## Alternatives Considered

### Apache Kafka (Rejected)

Kafka is the industry-standard event streaming platform. It offers configurable disk-based retention, true replay to arbitrary offsets, higher raw throughput, and a richer ecosystem. We rejected it for three reasons:

**Operational overhead exceeds team capacity.** A 6-person team without a dedicated infrastructure engineer cannot absorb Kafka's operational surface: broker tuning (heap, page cache, replication throttling), partition rebalancing, disk sizing for retention, monitoring (consumer lag, ISR status, request metrics), and failure recovery. Redis, which we already run, has a fraction of this surface area.

**Learning curve delays delivery.** Zero team Kafka experience means the 2-week delivery constraint is violated before we write a single line of application code. The team must learn: producer configuration (acks, idempotence, compression), consumer group coordination, offset management, exactly-once semantics boundaries, and partition strategy. Redis Streams reuse concepts the team already knows (Redis data structures, replication, persistence, monitoring).

**Unused capability at current scale.** Kafka's strengths — high throughput, long-term retention, multi-subscriber replay — are architectural capabilities we are not buying at 500 req/s peak and a 2-quarter horizon. They would become relevant at 100x growth and beyond, at which point migrating from Redis Streams to Kafka is a known, well-documented path that does not constrain the current design.

**Cost.** Self-hosted Kafka requires dedicated EC2 instances with attached EBS volumes sized for retention. Managed Confluent Cloud starts at significant monthly cost at production scale. Redis Streams use the existing cluster with negligible incremental cost.

### Amazon SQS + SNS (Deferred)

SQS provides a managed queue with at-least-once delivery, DLQ support, and configurable retry. SNS provides pub/sub fan-out. This was deferred because: (a) SQS does not natively support consumer groups for distributing messages across WebSocket server instances, which is a hard requirement for the 2-quarter WebSocket roadmap; (b) SNS topic filtering is less expressive than stream partitioning; (c) adding AWS-managed queue infrastructure increases cloud complexity and cost without offsetting benefit over the existing Redis investment. Worth revisiting if the team grows or if regulatory requirements mandate a fully managed solution.
