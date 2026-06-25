# ADR-001: Notification Subsystem Message Broker

**Status**: Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, 500 req/s peak) handles notifications — emails, webhooks, and soon WebSocket push — synchronously inside the HTTP request cycle. This causes request timeouts (800ms average, 8s spikes), silent failures with no retry or dead-letter queue, and cascading connection-pool exhaustion from slow webhook endpoints. Two production incidents this year trace back to this architecture.

Billing-critical notifications (trial expired, payment failed) require exactly-once delivery semantics. No such guarantee exists today.

We must decouple notification production from delivery, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing), and absorb 10x traffic growth without re-architecting. We also need to ship real-time WebSocket push within two quarters.

**Constraints:**

- 6-person engineering team (3 senior, 3 mid-level); no dedicated infrastructure engineer
- Redis already in production for sessions and rate limiting; team has operational familiarity
- No Kafka experience on the team
- Maximum 2 weeks of setup/migration before delivering value
- Modest budget — managed Confluent Cloud at full scale is not affordable

We are evaluating two options: **Apache Kafka** and **Redis Streams**.

## Decision

**We choose Redis Streams.**

Redis Streams satisfies every requirement at our current and projected scale while respecting the team, time, and budget constraints. Kafka is the stronger choice at extreme scale, but our 10x growth target (5,000 req/s peak) falls well within Redis's throughput envelope. The operational simplicity of extending an already-running Redis instance — versus standing up and maintaining an entirely new distributed system with no in-house expertise — is decisive.

Exactly-once semantics for billing notifications will be enforced at the application layer via an idempotency-deduplication table in PostgreSQL, not by relying on broker-level transactional guarantees. This is the same pattern both options would require in practice, and it keeps the implementation accessible to the team.

## Consequences

### Pros

- **Minimal time to value.** Redis Streams use the same Redis instance we already operate. The team can begin producing and consuming events within days, not weeks. No new infrastructure to provision, monitor, or patch.
- **Team velocity.** The team already understands Redis operations (persistence, replication, memory management). Adding Streams is a new data structure, not a new distributed system. Kafka would require learning broker topology, partition strategy, consumer rebalancing protocols, and ZooKeeper/KRaft operations from zero.
- **Sufficient throughput.** Redis Streams handle 100K+ writes/sec on a single instance. Our 10x growth target of 5,000 req/s peak leaves over an order of magnitude of headroom before horizontal scaling becomes necessary.
- **Consumer groups built-in.** `XREADGROUP`, `XACK`, and `XPENDING` provide consumer-group semantics with delivery tracking and retry. The API surface is small and well-documented, suitable for a small team to implement correctly in a short sprint.
- **Straightforward WebSocket path.** Redis Pub/Sub complements Streams for real-time fan-out (ephemeral push), while Streams provide durable, ordered persistence for guaranteed delivery. Both run on the same Redis instance the team already manages.
- **Cost efficiency.** No new infrastructure spend. The existing Redis instance (or a second dedicated instance at modest marginal cost) replaces what would otherwise require 3+ Kafka brokers plus monitoring.

### Cons

- **Message retention is not infinite.** Redis Streams require explicit retention policy (`MAXLEN` or time-based trimming). Unlike Kafka's configurable long-term retention, unacknowledged or unprocessed messages can be trimmed before delivery if policy is misconfigured. We mitigate this by setting generous retention (7 days) and alerting on `XPENDING` backlog depth.
- **No native exactly-once semantics.** Redis provides at-least-once delivery. For billing notifications, we implement application-level exactly-once using a PostgreSQL deduplication table keyed on a notification ID. This is the pragmatic approach — Kafka's exactly-once semantics require transactional producers and idempotent consumers, and most teams end up implementing application-level idempotency regardless.
- **Single-node availability risk.** Our current Redis is a single instance. If it goes down, notification production halts. We will configure Redis with AOF persistence and a replica for automatic failover (Redis Sentinel), which addresses availability within our budget and operational capacity.
- **Scaling ceiling.** Redis Streams cannot horizontally partition a single stream across nodes the way Kafka partitions across brokers. If we eventually exceed single-instance capacity, we can shard by notification type across multiple streams and instances, but this requires application-level routing logic. For 10x growth from our current baseline, this is not a near-term concern.
- **Smaller ecosystem.** Kafka has a richer ecosystem of connectors (Kafka Connect), schema registries, and monitoring tools (Confluent Control Center). Redis Streams has fewer third-party integrations. We accept this trade-off because our use case is a single internal notification pipeline, not a company-wide event backbone.

## Alternatives Considered

### Apache Kafka — Why we rejected it

Kafka is the industry-standard distributed event streaming platform and would be the correct choice for a larger organization with dedicated infrastructure engineers and a multi-team event streaming mandate. Its specific advantages over Redis Streams include:

- **Partition-level ordering with parallel consumption** across many consumers.
- **Configurable long-term retention** (days to weeks of replayable event history).
- **Transactional exactly-once semantics** at the broker level (idempotent producers + transactional consumers).
- **Mature ecosystem** (Kafka Connect, Schema Registry, ksqlDB, Confluent Platform).

However, Kafka is the wrong fit for our situation:

1. **Operational complexity exceeds team capacity.** Kafka requires managing broker clusters, partition assignment, replication factors, and either ZooKeeper or KRaft consensus. A 6-person team with no dedicated infra engineer and zero Kafka experience would face a steep learning curve and ongoing operational risk. Two production incidents from connection-pool exhaustion already signal the team is stretched; adding Kafka operations compounds the problem.

2. **Setup time violates the 2-week constraint.** Provisioning, configuring, and hardening a Kafka cluster (minimum 3 brokers for fault tolerance) plus building the producer/consumer integration would take 3–5 weeks for a team learning it from scratch. Redis Streams integration can ship in under 1 week.

3. **Budget.** Self-managed Kafka requires 3+ broker nodes, monitoring infrastructure, and ongoing maintenance. Managed Confluent Cloud is explicitly out of budget at full scale. Redis runs on our existing instance.

4. **Kafka's advantages are marginal at our scale.** Our projected peak of 5,000 req/s is well within single-instance Redis capacity. Kafka's horizontal scalability and million-msg/sec throughput solve problems we do not have.

5. **Exactly-once is not free in Kafka either.** Kafka's exactly-once semantics require transactional producers and consumers, careful consumer offset management, and still benefit from application-level idempotency for external side effects (sending an email, calling a webhook). In practice, the deduplication-table approach we plan with Redis is the same safety net most Kafka deployments implement alongside broker-level guarantees.

If the platform eventually grows to serve millions of MAUs, operates a multi-team event backbone, or requires multi-day event replay at high volume, we should re-evaluate Kafka. At that point, the team will have operational maturity from running Redis Streams and can evaluate the migration with real production data.