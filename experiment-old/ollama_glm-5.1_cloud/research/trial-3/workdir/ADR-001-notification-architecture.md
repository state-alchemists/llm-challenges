# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails, webhooks, and upcoming WebSocket pushes — synchronously inside the HTTP request cycle. This design has caused request timeouts (800ms avg, 8s spikes), silent delivery failures with no retry or dead-letter queue, two cascading outages from slow webhook endpoints exhausting the DB connection pool, and zero delivery guarantees for billing-critical notifications that require exactly-once semantics.

We need to decouple notification processing from the request cycle with an asynchronous system that supports retry with exponential backoff, at-least-once delivery for all events, exactly-once for billing events, and a path to real-time WebSocket push notifications within two quarters. The system must handle 10x traffic growth without re-architecting.

Key constraints:

- **6-person engineering team** (3 senior, 3 mid-level), no dedicated infra engineer.
- **Redis already in production** for sessions and rate limiting.
- **No Kafka experience** on the team.
- **2-week maximum** for setup and migration before delivering value.
- **Modest budget** — managed Confluent Cloud at full scale is not viable.
- **Exactly-once semantics required** for billing notifications.

Two candidates are on the table: Apache Kafka and Redis Streams.

## Decision

**We choose Redis Streams.**

Redis Streams addresses every requirement within the team's operational and temporal constraints, while Kafka introduces capability we cannot exploit and complexity we cannot sustain. The deciding factors:

1. **Setup time and operational fit.** We already run Redis in production and the team has operational fluency with it. Redis Streams requires enabling a new data structure on an existing cluster — not standing up a new distributed system. Kafka demands Zookeeper or KRaft, broker configuration, topic/partition planning, JVM tuning, and monitoring — all with no prior experience and no dedicated infra engineer. The 2-week constraint makes Kafka unrealistic without cutting corners on reliability.

2. **Throughput is sufficient.** At 500 req/s peak with a 10x growth target (5,000 req/s), Redis Streams handles this comfortably — single-node Redis processes 100k+ writes/s, and clustered deployments scale further. Kafka's theoretical throughput ceiling (millions of msgs/s) is 2–3 orders of magnitude beyond our needs. Paying that operational tax for unused headroom is a bad trade.

3. **Consumer groups and delivery guarantees.** Redis Streams supports consumer groups (XREADGROUP), pending entry lists for crash recovery (XPENDING/XCLAIM), and message acknowledgment (XACK). This gives us at-least-once delivery natively. For exactly-once billing semantics, we will use a deduplication table in PostgreSQL — the consumer writes a message-idempotency key to the DB before processing, and skips duplicates on retry. This is the standard pattern for exactly-once on top of at-least-once systems, and it works equally well in Redis Streams or Kafka. Kafka's transactional producer/consumer (exactly-once semantics via Kafka Transactions API) is more robust out of the box but requires Java consumers and significantly more configuration — a poor fit for a Python/Flask codebase.

4. **Message retention.** Kafka's unlimited retention is a strength for event sourcing; for a notification queue it is overkill. Redis Streams' maxlen-based trimming (e.g., MAXLEN ~1M) covers our retry window and audit needs. We will persist a compact notification log in PostgreSQL for long-term history, which we need regardless of the broker.

5. **WebSocket path.** Redis Pub/Sub (already available) is the natural fan-out layer for real-time push. Redis Streams handles the durable, ordered processing; Pub/Sub handles the ephemeral real-time fan-out. They compose cleanly under one operational umbrella. Kafka could serve both roles but adds nothing architecturally that Redis doesn't provide at our scale.

## Consequences

### Pros

- **Fast time to value.** Reusing an existing Redis deployment means we can ship consumer group-based async processing within the 2-week window. No new infrastructure to provision, monitor, or learn.
- **Lower operational burden.** The team already operates Redis (upgrades, failover, backups). Adding Streams is a dataset, not a new system. No JVM tuning, no partition rebalancing, no Zookeeper/KRaft to nurse.
- **Cost contained.** No additional infrastructure spend beyond modest memory scaling on the existing Redis nodes. Self-managed Kafka on EC2 would require 3+ brokers plus storage; managed Kafka (MSK, Confluent) exceeds the budget.
- **Sufficient performance.** Redis Streams at our scale (≤5k req/s after 10x growth) is well within single-node capacity. We retain the option to cluster if needed later.
- **Exactly-once via idempotency.** The PostgreSQL deduplication table gives billing notifications exactly-once semantics without requiring Kafka's transactional consumer protocol or Java infrastructure.

### Cons

- **Retention and replay limitations.** Redis Streams truncates by length or age (MAXLEN/MINID), not by arbitrary time-based compaction like Kafka. Long-term notification history must live in PostgreSQL, which is acceptable since we need it for audit/compliance regardless, but it does mean the broker is not the system of record.
- **No native exactly-once.** Achieving exactly-once for billing requires an application-level deduplication pattern (idempotency keys in PostgreSQL). This adds code and a DB dependency to the critical path. Kafka's transactional API provides this at the broker level — though only for Java consumers, which doesn't help a Python team.
- **Scaling ceiling is lower.** Redis Streams tops out well below Kafka in partitions, throughput, and data volume. If we ever exceed ~50k msg/s or need hundreds of partitions, migration to Kafka (or a system like Amazon SQS / Kinesis) becomes necessary. That would be a year+ away at current growth rates and would merit its own ADR.
- **Single point of failure risk.** A single Redis node is a SPOF. We must run Redis in a replicated (primary-replica with Sentinel or Redis Cluster) configuration before shipping, which adds moderate complexity to our existing setup. This is still far simpler than a Kafka cluster.
- **Less mature consumer group tooling.** Redis Streams consumer groups lack Kafka's mature ecosystem of monitoring dashboards, lag measurement tools, and rebalancing mechanics. We will need to build lightweight tooling for visibility (pending-entry monitoring, consumer health checks) — a few days of work, not weeks.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for durable, high-throughput event streaming. Its strengths — unlimited message retention, partition-based parallelism, Kafka Transactions for exactly-once, and a rich ecosystem of connectors and tooling — are real. However:

- **Operational complexity exceeds team capacity.** Six engineers with no Kafka experience and no dedicated infra role cannot reliably operate a Kafka cluster in production within 2 weeks. The failure modes (partition rebalancing, ISR shrinking, controller failover) require deep JVM and distributed-systems expertise.
- **Throughput is wasted.** Our peak is 500 req/s with a 10x target. Kafka is designed for 100k–1M+ msg/s. The operational cost of running Kafka at our scale is disproportionate to the value.
- **Exactly-once benefit is inaccessible.** Kafka's exactly-once semantics require the Java transactional producer/consumer API. Our stack is Python/Flask. The Confluent Python client supports idempotent producers but not the full transactional exactly-once flow. We would still need application-level deduplication — the same pattern we'd use with Redis Streams.
- **Budget.** Self-hosted Kafka on AWS requires minimum 3 m5.large brokers (~$250/mo) plus EBS storage. Managed options (MSK, Confluent) scale higher. Redis Streams adds ~$0 in infra cost beyond memory scaling on our existing nodes.

Kafka remains the right choice if we grew to 50M+ events/day, needed multi-team event sourcing, or hired a platform engineering team. None of those are true today or within the next 12 months.

### Other alternatives briefly evaluated

- **Amazon SQS + SNS.** Good fit for async processing with exactly-once (SQS FIFO + dedup IDs), but adds a cloud-provider lock-in concern and higher per-message cost at scale. Also requires learning and wiring two more AWS services. Viable but offers no advantage over Redis Streams given we already operate Redis.
- **RabbitMQ.** Mature, supports priority queues and dead-letter exchanges natively. But introduces a new system to operate (Erlang runtime, cluster management) with no existing team expertise. Redis Streams is the simpler choice given our existing Redis dependency.
- **Celery with Redis broker.** Gets us async processing quickly, and we could use it on top of Redis Streams. Celery's built-in retry and dead-letter handling would reduce application code. However, Celery's at-least-once guarantee and lack of native consumer-group concepts mean we'd still need the PostgreSQL dedup table for exactly-once. Celery is a reasonable addition in phase 2 to reduce boilerplate; it does not change the broker choice.