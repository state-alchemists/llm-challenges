# ADR-001: Notification Subsystem Architecture

## Status

**Proposed**

## Context

Our SaaS project-management platform currently processes notifications—emails and webhooks triggered by task lifecycle events—synchronously inside the Flask HTTP request cycle. At a peak load of ~500 req/s, this produces average latencies of 800 ms and spikes to 8 s, because each request waits for SMTP and downstream HTTP calls to complete. We have experienced two cascading-failure incidents this year when slow webhook endpoints exhausted our connection pools. Silent drops are common: if a provider is unreachable, the notification is lost with no retry mechanism, dead-letter queue, or audit trail.

Billing-critical events (e.g., "trial expired", "payment failed") must be delivered exactly once, yet today we have no idempotency or delivery guarantee of any kind.

Our constraints are tight:

- Engineering team of six (three senior, three mid-level), with **no dedicated infrastructure engineer**.
- We already operate a Redis instance in production (sessions, rate limiting).
- **Zero prior Kafka experience** on the team.
- The migration must begin delivering value within **two weeks**; we cannot spend a month standing up and tuning a new cluster before shipping.
- Budget is modest; a fully managed Kafka offering (e.g., Confluent Cloud) is not affordable at our projected scale today.
- We must support **10× traffic growth** (peak ~5,000 req/s) without another forced re-platforming.
- A real-time WebSocket push layer is planned within two quarters.

We therefore need an async message backbone that decouples notification dispatch from HTTP responses, provides durable buffering, supports retries with backoff, and gives us a plausible path to exactly-once delivery for billing events.

## Decision

**Adopt Redis Streams as the notification backbone.**

Redis Streams will be used to enqueue all notification jobs. Flask workers will publish events to typed streams (e.g., `stream:email`, `stream:webhook`, `stream:billing`). A pool of Python consumers running as background processes will read from these streams via consumer groups (`XREADGROUP`), acknowledge successful deliveries (`XACK`), and rely on `XPENDING` / `XCLAIM` to implement exponential-backoff retries. A retention policy based on `MAXLEN` or time-to-live (TTL) will bound memory usage.

Exactly-once semantics for billing events will be enforced **at the application layer**, not the broker layer. Each billing event will carry a deterministic idempotency key (derived from the billing record ID and event type). Consumers will upsert processing state into PostgreSQL with a unique constraint on that key before performing the side effect (e.g., sending the email). Because Redis Streams guarantees at-least-once delivery, the idempotent consumer guarantees exactly-once outcomes. This pattern is necessary even with Kafka—broker-level exactly-once does not prevent duplicate side effects in external systems—so it does not represent net-new engineering work.

This decision prioritizes operational simplicity and speed-to-value over the ultimate scalability headroom of a dedicated log broker. At our projected peak of 5,000 messages/second, a single well-provisioned Redis node (or a small Redis Cluster) is well within documented throughput limits. Should we eventually outgrow Redis Streams, the consumer-group abstraction and stream-offset model provide a clean migration path to Kafka without rewriting producers or consumer logic.

## Consequences

### Positive

- **Time-to-value**: Because Redis is already deployed and the team is familiar with its data structures, a basic streams-based pipeline can be wired into the existing Flask app in days, not weeks.
- **Operational simplicity**: A single managed Redis node (or AWS ElastiCache) requires far less tuning, monitoring, and partition rebalancing than a self-hosted Kafka cluster. There is no ZooKeeper or KRaft quorum to babysit.
- **Cost alignment**: We pay for the Redis instance we already run. Incremental cost for Streams usage is negligible compared with provisioning dedicated Kafka brokers or paying for managed Kafka at our message volumes.
- **Unified stack for real-time push**: Redis Pub/Sub is a standard substrate for WebSocket broadcast. Choosing Redis Streams now keeps our real-time roadmap on the same infrastructure, reducing future cognitive and operational overhead.
- **Sufficient throughput**: Redis can sustain 100,000+ simple operations per second on modest hardware. Stream operations are slightly heavier, but 5,000 msgs/s leaves ample headroom.
- **Ordering per stream**: Events within a single Redis Stream are strictly ordered by ID, preserving causal sequencing for notifications related to the same task.

### Negative

- **Memory-bound retention**: Redis is an in-memory store. Messages evicted by `MAXLEN` or TTL are gone; there is no cheap "infinite cold storage" equivalent to Kafka's disk-based log segments. We must size the instance carefully and accept bounded history (acceptable for notifications, which are ephemeral).
- **Weaker native durability**: Redis AOF/RDB persistence is configurable but not as robust as Kafka's replicated, fsynced commit log. A catastrophic simultaneous loss of master and snapshot would mean unacknowledged message loss. Mitigation: run Redis with AOF `appendfsync everysec` and immediate replica promotion.
- **Exactly-once is application-owned**: Unlike Kafka's idempotent producer + transactional consumer APIs, Redis Streams offers only at-least-once delivery. The burden of deduplication falls entirely on our consumer code. A bug in the idempotency table would lead to duplicate billing emails.
- **Consumer group maturity**: Redis Streams consumer groups lack the automatic partition rebalancing and offset-commit coordination found in Kafka. We must handle stalled consumers and ownership handoffs manually (or via a lightweight supervisor), which increases client-side complexity.
- **10× scale ceiling**: While 5,000 msgs/s is comfortable, 50,000 msgs/s (100×) or multi-day retention at high volume would exceed the practical limits of a single Redis instance. If we blow past that threshold, a later migration to Kafka will be necessary.

## Alternatives Considered

### Apache Kafka

Kafka was the primary alternative. It offers superior properties on paper for this use case:

- **Throughput**: A modest three-broker Kafka cluster can absorb hundreds of thousands of messages per second, dwarfing our 5,000 msgs/s ceiling.
- **Durability & retention**: Kafka stores messages on disk with configurable replication and retention, decoupling capacity from RAM.
- **Exactly-once semantics**: Kafka provides idempotent producers and transactional consumption (`isolation.level=read_committed`), giving stronger broker-level guarantees than Redis.
- **Consumer groups**: Mature, automatic rebalancing and offset management reduce client-side complexity.
- **Ecosystem**: Rich connector ecosystem (Kafka Connect) and schema evolution support (Schema Registry).

**Why it was rejected:**

The operational and human costs outweigh these advantages for our current stage.

1. **Operational complexity without an infrastructure engineer**: Self-hosting Kafka on AWS EC2 requires tuning JVM heap sizes, OS page caches, file descriptor limits, replication factors, and partition counts. Without a dedicated SRE, ongoing maintenance (rolling restarts, partition rebalances, disk-alert triage) will consume senior-engineering bandwidth that we need for product work.
2. **Timeline risk**: Even a minimal, production-hardened Kafka deployment—including bootstrap, replication, monitoring dashboards, and failure-runbook documentation—would realistically take three to four weeks, violating our two-week value-delivery mandate.
3. **Budget constraint**: Managed Kafka (MSK, Confluent Cloud, Upstash) removes operational burden but is priced for throughput tiers that become expensive quickly. Confluent Cloud is explicitly ruled out by our budget.
4. **Team experience gap**: None of our six engineers has operated Kafka in production. The learning curve for debugging consumer-lag storms, partition hot spots, and broker failures is non-trivial and would materially slow incident response.
5. **Duplicate side-effect risk remains**: Even Kafka's exactly-once guarantee covers only the broker-to-consumer handoff. If our consumer sends an email and then crashes before committing the Kafka offset, the message will be redelivered. We would still need the same PostgreSQL-based idempotency layer we are building for Redis. Therefore, Kafka does not eliminate the application-level exactly-once work; it only shifts the risk profile from "at-least-once from broker" to "at-least-once from broker plus broker-level deduplication."

Kafka is the right tool if we had an infrastructure team, a longer runway, and a budget for managed services. Under our present constraints—small team, tight deadline, modest budget, and no Kafka expertise—Redis Streams delivers the required capabilities faster and with lower operational risk.
