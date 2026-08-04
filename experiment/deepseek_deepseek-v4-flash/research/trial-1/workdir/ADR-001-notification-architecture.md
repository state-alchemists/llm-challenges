# ADR-001: Notification Architecture

**Status:** Proposed

## Context

The notifications module of our SaaS project-management platform sends email and webhook notifications when tasks are updated, assigned, or completed. Today those sends happen synchronously inside the HTTP request cycle, and that coupling is the root of four production problems (system_context.md:20-25):

1. **Request timeouts.** Average request latency is 800 ms and spikes to 8 s during peak hours because a notification blocks the response until the email provider or webhook endpoint answers.
2. **Silent failures.** When a provider or endpoint is down, the notification is dropped. There is no retry and no dead-letter queue.
3. **Cascading failures.** Twice this year a slow webhook exhausted the PostgreSQL connection pool and took down unrelated features.
4. **No delivery guarantees.** Billing-critical notifications ("trial expired", "payment failed") must not be lost, and the current system offers no guarantee at all.

The scaling target requires decoupling notifications from the request cycle, retry with exponential backoff, at-least-once delivery for billing events with exactly-once where feasible, real-time WebSocket push within two quarters, and 10x traffic growth without re-architecting (system_context.md:27-34).

The constraints shape this decision more than the feature lists do (system_context.md:36-43):

- Six engineers (three senior, three mid-level), no dedicated infrastructure engineer.
- Redis is already in production for sessions and rate limiting; the team already operates it.
- No Kafka experience on the team today.
- No more than two weeks of setup/migration work before delivering value.
- Modest budget: managed Confluent Cloud at full scale is unaffordable today.
- Billing notifications must maintain exactly-once semantics.

## Decision

We choose **Redis Streams** as the transport for the notification subsystem.

Redis Streams is the only option that satisfies every functional requirement while respecting every constraint. It is already in our stack, it is operable by a six-person team with no infrastructure specialist, it fits the two-week time-to-value window, and it has more than enough headroom for the stated growth target. Apache Kafka is a genuinely stronger event platform, but it is the wrong choice for this team, this timeline, and this budget: its decisive advantages are not the ones this system needs, and its operational cost is one we cannot pay.

**Functional fit.** Redis Streams (`XADD` / `XREADGROUP`) provides a durable, ordered, replayable queue with native consumer groups and an explicit acknowledgment protocol. The pending-entries list (PEL) gives at-least-once delivery: a worker acknowledges (`XACK`) only after the side effect succeeds, and a crashed worker's in-flight messages remain visible for redelivery via `XAUTOCLAIM`. Retry with exponential backoff is a worker-side loop over the PEL plus bounded re-enqueues; messages that exhaust their attempts go to a dedicated dead-letter stream. Throughput is a non-issue: a single Redis node sustains tens of thousands of stream operations per second on modest hardware (order-of-magnitude figure), while our projected load at 10x growth is roughly 2,000-5,000 notifications per second — about 10M notifications/month today from 2M tasks, even assuming a generous 100x peak-to-average ratio (system_context.md:5-8). That leaves 10x-30x headroom on one node.

**Exactly-once deserves a precise statement.** Kafka's transactional exactly-once (KIP-98) guarantees atomicity between producing and consuming *inside* Kafka; it cannot make an email send or a webhook call transactional, so true end-to-end exactly-once against external side effects is impossible in either system. The industry-standard guarantee — effectively-once, meaning at-least-once delivery plus consumer-side idempotency — is fully achievable with Redis Streams. Stream message IDs are deterministic (milliseconds-timestamp-sequence), so a consumer can deduplicate by ID with a unique index in PostgreSQL or `SETNX` in Redis, and the billing event can be persisted transactionally alongside the notification record in PostgreSQL so a reconciliation worker can backfill anything lost. This delivers "exactly-once where feasible" with the same practical guarantee Kafka would provide, at a fraction of the complexity.

**Future fit.** The same Redis instance will host the Pub/Sub channels that power the WebSocket push layer in two quarters, keeping a single piece of infrastructure in the loop. We will not deploy Apache Kafka at this time.

## Consequences

**Pros**

- **Decoupling and latency.** Notification work leaves the request cycle; HTTP latency drops to roughly the PostgreSQL write time instead of 800 ms-8 s.
- **Delivery guarantees.** At-least-once is native (PEL + `XACK`); effectively-once for billing is a small, well-understood consumer pattern; nothing is silently dropped.
- **Retry and dead-lettering.** Exponential backoff and a dead-letter stream are straightforward conventions on top of `XADD` / `XPENDING`.
- **Operational simplicity.** No new infrastructure, no new runtime, no new monitoring stack; the team already runs Redis. Time-to-value is days, not weeks, satisfying the two-week constraint.
- **Cost.** Redis is already budgeted; no managed-Kafka spend; one modestly sized node plus a replica covers 10x growth.
- **WebSocket path.** Redis Pub/Sub is the standard backplane for WebSocket fan-out (Socket.IO, Django Channels, ActionCable), so the two-quarter WebSocket target reuses the same system.

**Cons**

- **Memory-bound retention.** Redis Streams live in RAM. Long retention and deep replay cost memory, so streams must be capped with `MAXLEN` trimming; Redis is a short-horizon transport, not an audit log. Billing auditability must come from PostgreSQL, which we already plan for.
- **Durability caveats.** AOF with `appendfsync everysec` means up to roughly one second of messages can be lost on a hard crash; `appendfsync always` removes that at some throughput cost. Multi-AZ replication (ElastiCache or Sentinel) is required to avoid a single point of failure.
- **Ordering discipline.** Order is guaranteed per stream, but a consumer group distributes messages across consumers, so global order is not preserved. Order-critical paths must use a single consumer or a key-sharded stream design (for example, `notifications:user:{id}`). Kafka has the same limitation one level down (per-partition, not global), so this is not a regression.
- **Exactly-once is consumer-side responsibility.** The platform gives at-least-once; deduplication, idempotency keys, `XPENDING` monitoring, and lag alerts must be built and maintained by us.
- **Scaling ceiling.** A single Redis node is the throughput and memory ceiling; Redis Cluster mode adds operational complexity, and beyond that the architecture would need to change. The 10x target stays comfortably inside the single-node envelope, but a 100x target would reopen this decision.
- **Migration risk.** Redis Streams is not a drop-in Kafka replacement if requirements later demand long retention, replay for analytics, or multi-tenant isolation. We mitigate by defining a thin publish/handle interface now, so the transport can be swapped without rewriting producers or workers.

## Alternatives Considered

**Apache Kafka — rejected.**

Kafka is the stronger general-purpose event platform, and the properties that make it strong are real; the decision is about which properties this system needs.

- **Throughput.** Multi-broker Kafka clusters sustain millions of messages per second, orders of magnitude beyond our 10x projection of roughly 2,000-5,000/s. At our scale Kafka would be idle overprovisioning; Redis has 10x-30x headroom on a single node we already run.
- **Ordering.** Kafka guarantees order per partition and supports key-based partitioning; Redis guarantees order per stream. Both provide per-key order only if the key is the shard. Kafka is marginally more ergonomic here, not decisively better.
- **Retention and replay.** This is Kafka's strongest argument: disk-backed, time-and-size-based retention (`log.retention.*`) with true replay for analytics and audit. We do not need long replay today, and the billing audit trail lives in PostgreSQL regardless of transport. Paying Kafka's operational cost for retention we will not use fails the cost-benefit test.
- **Consumer groups.** Kafka's consumer groups are mature (rebalancing, committed offsets, lag metrics); Redis `XREADGROUP` covers our needs (multiple consumers, `XACK`, PEL, `XAUTOCLAIM`). Kafka's richer machinery also brings rebalance storms and offset-management footguns a six-person team would have to learn the hard way.
- **Exactly-once.** Kafka's EOS (idempotent producer plus transactions) is broker-internal. Against external side effects like email and webhooks it degrades to the same effectively-once pattern Redis requires — so the headline feature does not actually buy the billing guarantee.
- **Operational complexity — the decisive failure.** Kafka is a distributed system to operate: three or more brokers for high availability, KRaft/ZooKeeper coordination, partition and replication tuning, disk sizing, JMX monitoring, version upgrades, and consumer-rebalance debugging. With no Kafka experience and no infrastructure engineer, a safe, well-run cluster is realistically four to eight weeks of focused work — twice the entire budget — and managed Confluent Cloud at production scale exceeds the stated budget. Redis Streams has no equivalent barrier: it is new commands on infrastructure we already run.
- **WebSocket path.** Kafka would add a second system for what Redis Pub/Sub already does natively.

Verdict: Kafka is the right call at much larger scale, or when long retention and replayable event history become core product requirements. For a six-person team, a two-week deadline, a modest budget, and an existing Redis deployment, its strengths are surplus and its costs are unpayable. We reject it and will revisit only if the single-node Redis envelope is breached (roughly 100x current load) or long-horizon replay becomes a requirement.

Other candidates were considered briefly. AWS SQS offers managed at-least-once delivery but no ordering and limited replay, and it adds a second AWS integration without Redis's WebSocket story; RabbitMQ with Celery adds a new broker to operate without Kafka's throughput or Redis's existing footprint. Both lose to Redis Streams on the same constraint set.
