# ADR-001: Notification Subsystem — Kafka vs Redis Streams

**Status**: Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails and webhooks on task updates, assignments, and completions — **synchronously inside the HTTP request cycle**. This has caused request timeouts (avg 800ms, spikes to 8s), silent failures with no retry or dead-letter queue, two incidents of cascading connection-pool exhaustion from slow webhooks, and zero delivery guarantees for billing-critical notifications that require exactly-once delivery.

We need to decouple notification processing from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible for billing events), support real-time WebSocket push within two quarters, and handle 10x traffic growth (~5,000 req/s peak) without re-architecting.

Key constraints:

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Existing stack**: Redis already in production for sessions and rate limiting. No Kafka operational experience.
- **Timebox**: Must deliver value within 2 weeks of starting migration.
- **Budget**: Modest — managed Confluent Cloud at scale is not affordable today.
- **Semantic requirement**: Exactly-once delivery for billing notifications.

## Decision

**Choose Redis Streams as the notification subsystem message broker.**

Justification follows from the constraints. Both Kafka and Redis Streams satisfy the functional requirements, but they diverge sharply on operational fit:

| Factor | Apache Kafka | Redis Streams | Weight in this decision |
|---|---|---|---|
| Throughput at our scale | ~1M+ msgs/s | ~1M+ msgs/s | Neutral — both far exceed our 5k req/s target |
| Consumer groups | Native, mature | Native (XGROUP/XREADGROUP/XPENDING/XCLAIM) | Slight Kafka edge, but Redis Streams sufficient |
| Ordering guarantees | Per-partition strict | Per-stream strict (auto-incrementing IDs) | Equivalent for our single-stream model |
| Message retention | Configurable, days-to-infinite | Configurable (MAXLEN, time-based trimming) | Kafka superior for long retention; we need hours, not months |
| Exactly-once semantics | Idempotent producer + transactions within Kafka | At-least-once; exactly-once via app-level idempotency | See analysis below |
| Operational complexity | High — ZooKeeper/KRaft, partition mgmt, rebalancing, monitoring | Low — single Redis instance already running | **Decisive** |
| Team experience | None | Redis already in daily use | **Decisive** |
| Setup time | 3–6 weeks (learning + infra) for this team | 2–5 days | **Decisive** given 2-week constraint |
| Cost | Self-managed: high ops cost; Managed (Confluent): $$$$ | Already paid for | **Decisive** given budget constraint |

The three decisive factors — operational complexity, team familiarity, and time-to-value — all favor Redis Streams. The 2-week delivery constraint alone eliminates Kafka for this team; no one on the team has operated a Kafka cluster, and the learning curve for partition assignment, consumer rebalancing, and monitoring would blow past the deadline before producing a single working notification.

On exactly-once semantics, Kafka's transactional exactly-once applies *within the Kafka ecosystem* (producer → broker → consumer). Our actual end-to-end path is producer → broker → consumer → external service (SendGrid, webhook endpoint). The external call is the hard part, and Kafka's transactional guarantee does not cover it. Both systems require **application-level idempotency** to achieve true exactly-once delivery to an external system — a deterministic notification ID persisted in PostgreSQL and checked before dispatch eliminates duplicates regardless of the message broker. Redis Streams' at-least-once guarantee, combined with an idempotency table, achieves the same end-to-end guarantee Kafka would give us.

## Consequences

**Pros:**

- **Immediate value within the timebox.** Redis Streams uses the Redis instance we already run and the team already monitors. A working producer (XADD) and consumer group (XGROUP/XREADGROUP) can be wired in days, not weeks.
- **No new infrastructure to operate.** No ZooKeeper, no KRaft, no partition rebalancing to debug at 2 AM, no separate monitoring stack. Our existing Redis alerts, backups, and runbooks apply.
- **Sufficient throughput for 10x growth.** Redis Streams handles millions of messages per second on modest hardware. Our 10x peak (~5,000 req/s) is trivial.
- **Consumer groups are built-in.** XGROUP, XREADGROUP, XPENDING, and XCLAIM give us fan-out, load balancing across workers, claim-recovery for failed consumers, and a pending-entries list for retry — everything the notification pipeline needs.
- **Exact ordering per stream.** Redis Stream entries carry monotonically increasing timestamps, giving us strict FIFO within a stream — the ordering model we need for task lifecycle notifications.
- **Lower cost.** No new infrastructure line item; we pay for Redis already.

**Cons:**

- **No native exactly-once.** We must implement application-level idempotency (a `notification_id` column with a unique constraint in PostgreSQL, checked before each external send). This is a small amount of additional code and a PostgreSQL lookup per notification.
- **Memory-bound retention.** Redis Streams retain messages in memory (with optional offloading to disk via RDB/AOF). Very long retention (weeks/months) is infeasible, but our use case only needs hours — consumer lag is typically seconds to minutes. We will set `MAXLEN ~` to cap stream size and prevent unbounded growth.
- **No built-in schema registry.** Message format is a contract we enforce at the application layer. This is fine for our two consumer types (email, webhook) but would become a concern at dozens of independent consumer teams.
- **Single Redis node is a SPOD.** We should plan for Redis Sentinel or Cluster before the 10x growth target. This is already a concern for our existing session/rate-limiting use; the notification workload adds urgency but not novelty.
- **Fan-out to multiple consumer groups requires careful stream design.** If we later need dozens of independent consumer groups (e.g., audit logging, analytics, search indexing all reading the same stream), Kafka's topic-partition model is more natural. For our two consumer types, this is not a concern today.
- **Replay is less ergonomic.** Kafka's long retention makes reprocessing historical data straightforward. Redis Streams can replay only what hasn't been trimmed. We mitigate this by persisting all notification events in PostgreSQL as the system of record; replay means re-querying PostgreSQL, not re-reading the stream.

## Alternatives Considered

**Apache Kafka** was the strongest alternative. Its strengths — configurable long-term retention, native exactly-once transactions, mature ecosystem (schema registry, Kafka Connect, MirrorMaker), and proven scale at organizations orders of magnitude larger than us — are real. We rejected it for this phase because:

1. **No team experience.** None of our 6 engineers have operated Kafka in production. The learning curve (partition design, consumer rebalancing, offset management, monitoring with Burrow/jmx) would consume far more than 2 weeks before we shipped any user-facing value.
2. **Operational overhead without an infra engineer.** Running Kafka reliably requires dedicated capacity for cluster management, capacity planning, and incident response. A team of 6 with no infra specialist cannot sustain this without slowing feature delivery.
3. **Cost.** Self-managed Kafka on AWS requires 3+ broker nodes (minimum for replication), plus ZooKeeper or KRaft nodes. Managed Confluent Cloud at our scale starts at several hundred dollars/month and grows with throughput. Our budget does not support either option today.
4. **Diminishing returns at current scale.** Kafka's advantages over Redis Streams appear at very high partition counts, multi-datacenter replication, and ecosystem integrations. At ~5,000 req/s peak with two consumer types, Redis Streams provides all the functional guarantees we need.

We will revisit Kafka if and when the notification subsystem grows to require multi-team fan-out, multi-datacenter replication, or retention measured in weeks rather than hours. The idempotency-layer abstraction we build around Redis Streams will make that migration straightforward: the producer and consumer contracts stay the same; only the broker implementation changes.