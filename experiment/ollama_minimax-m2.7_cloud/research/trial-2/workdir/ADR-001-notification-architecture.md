# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

---

## Context

Our SaaS project management platform handles ~2M task events per month with a peak of ~500 req/s. The notification module — which sends emails and webhooks on task updates, assignments, and completions — runs synchronously inside the HTTP request cycle. This has caused request timeouts averaging 800ms (spiking to 8s), silent failures on downstream outages, cascading connection pool exhaustion taking down unrelated features, and no delivery guarantees for billing-critical notifications.

We need to decouple notifications from the request cycle, add retry with exponential backoff and a dead-letter queue, guarantee at-least-once delivery for billing events and exactly-once where feasible, and support WebSocket push notifications within two quarters — all while handling 10x traffic growth.

**Constraints:**
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience on the team
- Already running Redis for session storage and rate limiting
- 2-week maximum setup/migration before delivering value
- Modest budget; cannot afford managed Confluent Cloud at full scale
- Exactly-once semantics required for billing notifications

---

## Decision

**Use Redis Streams as the notification subsystem message broker.**

Redis Streams meets our throughput requirements (500 req/s × 10x = 5,000 req/s peak is well within Redis Streams' practical range of 10–50K messages/sec on commodity hardware), delivers the delivery guarantees we need, and leverages existing Redis infrastructure and expertise with minimal operational overhead. The team can implement a working system within two weeks and iterate from there.

### Why Redis Streams over Kafka

The core reason is fit to constraints: we already run Redis, the team knows Redis, and we can deliver value in under two weeks with no new infrastructure to operate. Kafka's operational complexity — requiring dedicated brokers, ZooKeeper or KRaft mode, partition-aware producers/consumers, and rebalancing tuning — introduces a substantive gap between "shipping a prototype" and "running reliably in production" that a 6-person team without Kafka experience cannot close in that window.

Specifically:

**Throughput adequacy.** Our peak target is 5,000 notifications/sec. Redis Streams on a single instance handles 10–50K messages/sec in practice (confirmed by Redis documentation and production benchmarks from Shopify, Discord, and similar high-traffic deployments). We are not in the 100K+ range where Kafka's linear scaling advantages become necessary. Redis Streams with consumer groups and pipelining is sufficient.

**Ordering guarantees.** Redis Streams guarantee ordering within a consumer group. For a given notification stream, all messages for the same entity (e.g., a task) will be delivered in order to the same consumer, preventing out-of-order delivery of related notifications. This is sufficient for our use case.

**Exactly-once for billing events.** Redis Streams supports consumer group acknowledgment (`XACK`), and we can implement idempotency keys stored in Redis (or PostgreSQL) to achieve exactly-once semantics for billing-critical notifications. When a worker processes a billing event, it writes the event ID to a deduplication set with a TTL; duplicate submissions are filtered before sending. This pattern is well-understood and avoids the configuration overhead of Kafka transactions.

**Operational simplicity.** Redis is already in our stack. We do not need to provision new servers, configure ZooKeeper, tune JVM heap sizes, or manage partition rebalancing. Consumer group management (`XREADGROUP`, `XACK`, `XPENDING`) is built into Redis and accessible via any Redis client library. Troubleshooting is familiar territory.

**Dead-letter queue support.** We can model dead-letter queues as separate Redis streams per notification type (e.g., `notifications:email:dlq`, `notifications:webhook:dlq`). Failed messages are moved to the DLQ after max retry attempts; an operator can inspect and replay from the DLQ.

**Migration path.** Since the Flask monolith already uses Redis for sessions, we can add a Redis Streams producer alongside the existing synchronous notification code and run both in parallel during migration. This staged rollout is lower-risk than a cutover to Kafka.

---

## Consequences

### Pros

1. **Fast time-to-value.** No new infrastructure to learn, provision, or operate. The team uses existing Redis clients and patterns. A functional producer-consumer pipeline is achievable in days, not weeks.
2. **Sufficient throughput.** 5,000 notifications/sec is well within Redis Streams' practical capacity. We can scale horizontally by adding consumer group instances, not by repartitioning.
3. **Exactly-once for billing.** Idempotency keys with Redis-set deduplication give us exactly-once semantics for billing-critical notifications without Kafka's transaction overhead.
4. **At-least-once for general notifications.** Consumer group acknowledgment with retry-on-failure covers general notifications.
5. **Dead-letter visibility.** Separate DLQ streams per notification type give operators a clear view of failures and replay capability.
6. **Low operational overhead.** No new processes to monitor beyond Redis itself, which we already run.
7. **Existing Redis expertise.** Troubleshooting, monitoring, and capacity planning leverage existing team knowledge.

### Cons

1. **Memory-bound retention.** Redis Streams stores messages in memory; retention is limited by available RAM. At high volume with long backlogs, memory becomes a constraint. Mitigation: configure `MAXLEN` or `MAXLEN~` (approximate trimming) to cap stream size; route long-retention events (e.g., audit logs) to PostgreSQL instead.
2. **Single-node bottleneck risk.** A single Redis instance is a single point of failure. Mitigation: deploy Redis in Sentinel (1 primary + 2 replicas) for automatic failover; use `READONLY` commands on replicas for consumer groups during read-heavy workloads. At our scale, this is manageable.
3. **Scaling ceiling.** Redis Streams scales to ~50K messages/sec on a single instance. If traffic grows beyond 10x (50,000+ notifications/sec), we would need to shard across multiple Redis instances (via consistent hashing) or migrate to Kafka. This is not a near-term concern.
4. **No native replay from offset.** Kafka allows rewinding to any offset; Redis Streams `XREADGROUP` only reads new messages. For bulk replay, you must consumer-copy messages. Mitigation: use `XRANGE` with start/stop IDs for one-off replays; automate via a small script.
5. **Less mature ecosystem tooling.** Kafka has battle-tested connectors (Debezium, Elasticsearch, S3), schema registry, and monitoring dashboards. Redis Streams tooling is less standardized; we would build more ourselves.

---

## Alternatives Considered

### Apache Kafka

**Rejected.** Kafka offers superior throughput (100K+ messages/sec), durable disk-based retention, and native exactly-once semantics via transactions — properties that make it the right choice for large-scale, multi-team architectures. However, for our constraints:

- **No existing expertise.** The team has no Kafka experience; the learning curve for producers, consumers, partition strategies, broker configuration, and replication is steep. "Two weeks to deliver value" is unrealistic for a team starting from zero.
- **Operational overhead.** Running Kafka requires at minimum 3 brokers for reasonable durability, plus ZooKeeper or KRaft management. Without a dedicated infrastructure engineer, this becomes a significant operational burden.
- **Budget.** Confluent Cloud at our scale (5,000 messages/sec, 3 brokers, cross-zone replication) costs several thousand dollars per month — beyond our modest budget. Self-hosting requires EC2 instances for Kafka brokers, ZooKeeper nodes, and monitoring, adding operational cost and complexity.
- **Over-engineering.** Our peak throughput is 5,000 notifications/sec, not 500,000. We are not solving a Kafka-scale problem; introducing Kafka to solve a Redis Streams-scale problem adds complexity without commensurate benefit.

Kafka would be reconsidered if traffic grew beyond ~50K notifications/sec, we added multiple downstream systems needing fan-out, we required cross-datacenter replication, or we onboarded a dedicated infrastructure engineer.

---

## Summary

Redis Streams is the right tool for this problem given our team size, existing infrastructure, timeline, and traffic profile. It delivers async notification processing, retry with exponential backoff, at-least-once delivery, and exactly-once semantics for billing events — without new infrastructure, without a steep learning curve, and within our two-week delivery constraint.