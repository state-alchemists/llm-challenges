# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails and webhooks triggered by task updates, assignments, and completions — synchronously inside the HTTP request cycle. This causes three critical problems:

1. **Request timeouts** — notification sending blocks responses (800ms avg, 8s spikes at peak).
2. **Silent failures** — no retry, no dead-letter queue; dropped notifications on provider/endpoint failures.
3. **Cascading failures** — two incidents this year where slow webhook endpoints exhausted the DB connection pool, taking down unrelated features.

Additionally, billing-critical notifications (trial expiration, payment failure) require exactly-once delivery semantics, which the current system cannot guarantee.

We need to decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing where feasible), add real-time WebSocket push within 2 quarters, and handle 10x traffic growth without re-architecting.

**Constraints:**
- 6-person team (3 senior, 3 mid-level), no dedicated infra engineer.
- Redis already in production for sessions and rate limiting.
- No Kafka operational experience on the team.
- Setup/migration must deliver value within 2 weeks.
- Modest budget — managed Confluent Cloud at scale is not affordable today.

## Decision

We choose **Redis Streams** as the notification subsystem's message backbone.

### Justification

The deciding factors map directly to the constraints:

1. **Operational complexity.** Redis is already running in our environment, monitored, and understood by the team. Introducing Kafka means provisioning a new cluster (or paying for Confluent Cloud), learning a fundamentally different operational model (brokers, ZooKeeper/KRaft, topic partitioning, log compaction), and maintaining it with zero prior experience and no dedicated infra engineer. Redis Streams requires no new infrastructure — we add stream commands to an existing, battle-tested deployment.

2. **Time to value.** The 2-week constraint is the hard boundary. A team with no Kafka experience realistically needs 1–2 weeks just to become competent with Kafka's deployment topology, producer/consumer configuration, and operational playbooks. Redis Streams can be integrated into the existing Flask monolith in days: `XADD` to produce, `XREADGROUP` with consumer groups to consume, `XACK` for delivery confirmation. The notification workers are straightforward Python processes, not a new distributed system.

3. **Throughput adequacy.** At 500 req/s peak and a 10x growth target of 5,000 req/s, Redis Streams comfortably handles the load. A single Redis node processes 100k+ commands/second; even accounting for stream-specific overhead and network round trips, our 10x target is well within capacity. Kafka's throughput advantage (millions of messages/second) is irrelevant — we are orders of magnitude below the ceiling where that matters.

4. **Delivery guarantees.** Redis Streams with consumer groups (`XREADGROUP`) provides at-least-once delivery. For billing notifications requiring exactly-once semantics, we implement idempotency at the consumer layer using PostgreSQL as the deduplication store (insert notification ID with a unique constraint; skip if duplicate). This is the standard pattern for exactly-once over at-least-once infrastructure, and it works because our consumers already have database access. Kafka's transactional exactly-once semantics (EOS) are stronger in theory, but they require careful producer/consumer configuration and add significant operational complexity — for our volume and team size, database-level idempotency is simpler and equally reliable.

5. **Consumer groups.** Redis Streams support consumer groups natively (`XGROUP`, `XREADGROUP`, `XACK`, `XPENDING`), giving us the fan-out, retry, and dead-letter semantics we need. Pending entries that are not acknowledged can be claimed by another consumer (`XCLAIM`), providing automatic failover. This covers the retry-with-backoff requirement: a worker claims a pending message after a timeout, processes it, and acknowledges it.

6. **WebSocket future.** The planned real-time push layer publishes to a Redis Stream; WebSocket servers subscribe via `XREADGROUP`. This is a natural fit — Redis Pub/Sub is the common pattern for WebSocket fan-out, and Streams adds the persistence and consumer-group semantics we need for delivery tracking. No re-architecture required.

7. **Budget.** No additional infrastructure cost. Our existing Redis instance handles the additional stream workload (we monitor memory and can scale vertically or add a dedicated Redis node for ~$50/month if needed). Managed Kafka starts at hundreds of dollars per month and scales into the thousands at our 10x target.

## Consequences

### Pros

- **Fast delivery.** Redis Streams integrate into the existing codebase and deployment within days, not weeks. The notification worker is a small Python process consuming from streams — minimal new code, minimal new operational surface.
- **No new infrastructure.** No new cluster to deploy, monitor, patch, or upgrade. Redis is already in our runbook.
- **Sufficient performance.** Redis Streams handle orders of magnitude more throughput than our 10x growth target. No performance ceiling risk within the planning horizon.
- **At-least-once with idempotent exactly-once.** Consumer groups + PostgreSQL deduplication gives us reliable exactly-once for billing notifications without the operational overhead of Kafka transactions.
- **Consumer group semantics.** Built-in support for fan-out, pending-entry retry, and claim-based failover maps directly to our retry-with-backoff and reliability requirements.
- **Cost.** Zero marginal infrastructure cost at current scale; linear and predictable scaling (vertical then a second node) rather than the step-function cost of managed Kafka tiers.
- **WebSocket path.** Streams naturally support the planned real-time push layer without architectural changes.

### Cons

- **Message retention is memory-bound.** Redis Streams retain messages in memory (with optional disk persistence via RDB/AOF). At our 10x target (~5,000 notifications/s sustained), long retention windows consume significant memory. We mitigate this with `MAXLEN` trimming on streams (e.g., `XADD ... MAXLEN ~ 1000000`) and by processing acknowledgments promptly. Kafka's disk-based retention is more efficient for very long retention, but our use case needs minutes-to-hours of retention, not weeks.
-. **No native log compaction.** Kafka can compact a topic to retain only the latest value per key, which is useful for state snapshots. Redis Streams have `XTRIM` by count or time, but no key-based compaction. For notifications (event-driven, not state snapshots), this is not a limitation; if we later need state-stream patterns, we will evaluate Kafka at that time.
-. **Single-node availability.** A standalone Redis instance is a single point of failure. We mitigate this with Redis Sentinel (already planned for the existing Redis deployment) for automatic failover, and AOF persistence for crash recovery. Redis Cluster is available if we later need horizontal sharding, but it adds complexity we do not need today.
-. **Scaling ceiling.** Redis Streams top out at single-node throughput (mitigated by clustering). If we grow beyond ~100k messages/second — which would be a 200x increase from current load — we would need to re-evaluate. This is outside the 10x planning horizon and would indicate a fundamentally different scale of business warranting a dedicated messaging platform.
-. **Smaller ecosystem.** Kafka has a richer ecosystem of connectors, schema registries, and tooling. Redis Streams has fewer third-party integrations. For our use case (producing from Flask, consuming in Python workers, with WebSocket delivery), we need no connectors; this gap does not apply.
-. **Monitoring maturity.** Kafka has more mature observability tooling (consumer lag dashboards, broker metrics). Redis Streams metrics are available via `XINFO` and Redis INFO, but require custom dashboarding. We budget ~1 day to build a lightweight monitoring view on top of our existing metrics pipeline.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event streaming platform, and it is objectively superior in several dimensions: disk-based retention with configurable retention policies, native log compaction, exactly-once semantics via transactional producers and consumers, multi-tenant topic isolation, and a mature ecosystem (Kafka Connect, Schema Registry, ksqlDB).

We rejected Kafka for this decision based on the following:

- **Operational overhead.** Deploying and operating Kafka (or paying for Confluent Cloud) requires specialized knowledge we do not have on the team. With no dedicated infra engineer, the operational burden of broker management, partition rebalancing, and monitoring falls on a team already maintaining a monolith and PostgreSQL. This risk is disproportionate to our current scale.
- **Time to value.** Kafka's learning curve — producer configuration, consumer group management, offset handling, partition strategies — means we would spend most of the 2-week window on infrastructure setup before writing a single notification worker. Redis Streams lets us ship the decoupled notification pipeline within the constraint.
- **Overengineering at current scale.** Kafka's strengths (multi-million msg/s throughput, multi-day retention, multi-consumer replay) solve problems we do not have. Our peak is 500 req/s, our 10x target is 5,000 req/s, and our retention need is minutes-to-hours. Deploying Kafka for this is like using a cargo plane for a commuter route.
- **Cost.** Self-hosted Kafka on AWS requires 3+ brokers for production resilience (~$500–$1,000/month in EC2), plus operational overhead. Confluent Cloud starts at ~$0.99/GB in/out plus per-partition costs, which at our 10x target exceeds our budget. Redis Streams add zero cost to our existing Redis deployment.
- **Reversibility.** If we outgrow Redis Streams, migrating from Redis Streams to Kafka is a well-understood path: we swap the producer backend and consumer group implementation. The surrounding architecture (workers, idempotency layer, retry logic) stays the same. Choosing Kafka first locks us into its operational model with no easy reversal.

### Redis Pub/Sub (without Streams)

Redis Pub/Sub provides fire-and-forget messaging with no persistence, no consumer groups, and no delivery acknowledgment. It is simpler than Streams but fails to meet our core requirements: no retry, no at-least-once delivery, no dead-letter handling. It would leave us with the same silent-failure problem we have today. Rejected.

### AWS SQS + SNS

Managed, reliable, and operationally simple. However: SQS does not support consumer groups natively (each queue is single-consumer or requires manual fan-out via SNS), exactly-once processing requires FIFO queues with a 300 msg/s throughput limit per queue (below our current peak), and the per-request pricing model becomes expensive at scale. We would also add a new AWS service dependency outside our current operational model. Rejected due to throughput constraints on FIFO queues and lack of native consumer-group fan-out.

### RabbitMQ

Feature-rich message broker with dead-letter exchanges, retry logic, and exactly-once-like delivery via message acknowledgments. However: it is a new infrastructure component we have no experience operating, its throughput model is per-queue rather than per-stream (creating scaling friction for high-volume notification channels), and it introduces another system to monitor and upgrade. Redis Streams solve the same problem with less new operational surface. Rejected.