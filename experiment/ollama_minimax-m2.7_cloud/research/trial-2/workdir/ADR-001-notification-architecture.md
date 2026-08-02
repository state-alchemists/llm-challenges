# ADR-001: Notification Subsystem Message Broker Selection

## Status

**Proposed**

## Context

We operate a SaaS project management platform serving 85,000 monthly active users, with peak load of ~500 req/s and ~2M tasks created monthly. The current notification module executes synchronously inside the HTTP request cycle, causing:

1. **Request timeouts** — notification delivery adds 800ms average latency, spiking to 8s under load
2. **Silent failures** — dropped notifications with no retry or dead-letter queue
3. **Cascading failures** — two incidents where slow webhook endpoints caused connection pool exhaustion, affecting unrelated features
4. **No delivery guarantees** — billing-critical notifications (trial expired, payment failed) lack exactly-once semantics

We need to decouple notification processing from the request cycle, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), and position ourselves for WebSocket push notifications within two quarters. The system must handle 10x traffic growth without re-architecting.

**Constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Existing Kafka experience: none
- Existing Redis experience: significant (session storage, rate limiting)
- Migration timeline: ≤2 weeks to production value
- Budget: modest; cannot afford managed Confluent Cloud at scale
- Existing infrastructure: PostgreSQL primary + read replica, Redis cluster, 4 web servers on AWS

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

Redis Streams provides sufficient throughput for our current and projected load, integrates with our existing Redis infrastructure, carries minimal operational overhead for a team already fluent in Redis, and can be production-ready within our 2-week constraint. For billing notifications requiring exactly-once semantics, we will implement idempotency keys at the application layer.

## Consequences

### Pros

1. **Operational familiarity** — The team already operates Redis for session storage and rate limiting. No new infrastructure to learn, monitor, or debug under pressure.
2. **Fast migration** — Redis Streams requires no new services. A working prototype is achievable in days; production-ready implementation fits within the 2-week constraint.
3. **Sufficient throughput** — Redis Streams handles 100,000–1,000,000 messages/second on commodity hardware. Our current peak of ~500 req/s, growing to 5,000 req/s under 10x growth, is well within range. Even accounting for multiple notifications per task event, headroom is ample.
4. **Ordering guarantees** — Redis Streams maintains insertion order within a stream. For notification ordering (e.g., "task assigned" before "task completed"), this is sufficient.
5. **Consumer groups** — XREADGROUP provides mature consumer group semantics with XACK for acknowledgment-based processing, enabling reliable retry logic.
6. **Existing Redis deployment** — No additional infrastructure cost. We can run notification streams on our existing Redis cluster alongside session data (with appropriate key isolation).
7. **WebSocket readiness** — Redis pub/sub integrates naturally with WebSocket push notifications. A future architecture can subscribe to notification streams and push events to connected clients without additional message broker complexity.
8. **Retry and dead-letter handling** — Consumer groups with PEL (Pending Entry List) tracking enable reliable retry with exponential backoff. Failed messages after N retries can be moved to a dead-letter stream for manual inspection.

### Cons

1. **No native exactly-once semantics** — Redis Streams provides at-least-once (via XACK) but not exactly-once. Billing notifications requiring exactly-once must be implemented via application-level idempotency keys (e.g., store a deduplication key in Redis with TTL after each processed notification).
2. **Message retention limits** — Redis Streams have a max stream size (512GB by default, configurable) and memory footprint considerations. For high-volume notification streams, we must configure appropriate MAXLEN policies or use XTRIM to bound memory usage.
3. **No native message replay for consumers** — Unlike Kafka's offset-based replay, Redis Streams consumers start from the current head by default. New consumer instances need explicit positioning (via XREAD or XREADGROUP with $). This requires discipline when adding new notification types or debugging.
4. **Operational limits at extreme scale** — If the platform grows to 10x beyond our projected 10x (100x current load), Redis Streams could become a bottleneck. Kafka would scale more gracefully. However, this is outside our 2-year planning horizon.
5. **Single-stream fan-out complexity** — Complex routing (e.g., sending different notification types to different processors) requires either multiple streams or application-level routing logic. Kafka's topic-per-event-type model is more natural here.
6. **No native schema evolution** — Notification payload schema changes require application-level versioning. Kafka's schema registry provides stronger governance, though this is manageable with discipline.

## Alternatives Considered

### Apache Kafka

Kafka is the industry standard for high-throughput event streaming and offers:

- **Native exactly-once semantics** (EOS) via Kafka Transactions
- **Superior throughput** (millions of messages/second with proper partitioning)
- **Topic-based routing** with natural separation of notification types
- **Massive retention** (days, weeks, or years of message history)
- **Mature ecosystem** (Kafka Streams, ksqlDB, schema registry)

However, we reject Kafka for this implementation because:

1. **No team experience** — The team has zero Kafka experience. Operational knowledge (broker configuration, partition rebalancing, replication factor, consumer lag monitoring) has a steep learning curve under production pressure.

2. **Operational complexity** — A production-ready Kafka deployment requires ZooKeeper (or KRaft in newer versions), proper broker sizing, replication factor configuration, and monitoring infrastructure. For a 6-person team with no dedicated SRE, this creates operational risk.

3. **Migration timeline** — A production-ready Kafka setup (cluster sizing, consumer group implementation, dead-letter handling, monitoring dashboards) realistically requires 4–6 weeks, not the 2-week constraint we have.

4. **Infrastructure cost** — While self-hosted Kafka on EC2 is cheaper than Confluent Cloud, the compute requirements (multiple brokers for replication, plus ZooKeeper nodes) exceed our current Redis footprint. At our scale (500 req/s peak, growing to 5,000 req/s under 10x growth), Kafka is significantly over-engineered.

5. **Over-engineering for requirements** — Kafka's strengths (millions of msg/sec throughput, multi-day retention, cross-datacenter replication) far exceed our needs. We would pay full operational complexity for headroom we will not use in the planning horizon.

**Kafka is the correct choice** if we had a dedicated platform/infrastructure team, expected 100x+ scale, required multi-day message retention for audit trails, or needed cross-datacenter replication. Given our constraints, the operational burden outweighs the technical benefits.

## Recommendation

Implement the notification subsystem using Redis Streams. Begin with a single stream per notification category (email, webhook, push) with consumer groups for each worker type. Use application-level idempotency keys for billing notifications. Monitor stream length and consumer lag; re-evaluate at 50x current load or if operational complexity of Redis stream management exceeds the team.

Redis Streams provides the right balance of capability, operational simplicity, and migration speed for our current constraints.
