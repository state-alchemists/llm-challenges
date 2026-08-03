# ADR-001: Notification Architecture — Adopt Redis Streams for Async Notification Processing

## Status

Proposed

## Context

Our SaaS project management platform currently processes notifications (emails, webhooks) synchronously inside the HTTP request cycle. At 85,000 monthly active users and peak loads of ~500 req/s, this design produces:

- **Request timeouts**: Average notification latency of 800 ms, spiking to 8 s during business hours.
- **Silent failures**: No retry or dead-letter mechanism when downstream providers are unavailable.
- **Cascading failures**: Slow webhook endpoints have twice exhausted connection pools, degrading unrelated features.
- **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") can be dropped or duplicated.

We must decouple notification dispatch from the HTTP request path, add retries with exponential backoff, and guarantee at-least-once delivery for all events and exactly-once semantics for billing notifications. Within two quarters we also intend to layer real-time WebSocket push notifications on top of the same infrastructure. The solution must support 10× traffic growth without forcing another re-architecture.

**Team and infrastructure constraints:**

- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis is already in production (session storage, rate limiting).
- No prior Kafka experience.
- Migration must deliver value within two weeks.
- Budget is modest; managed Confluent Cloud or large MSK clusters are not viable today.

## Decision

We will use **Redis Streams** as the messaging layer for the notification subsystem.

### Justification

1. **Operational fit for the team size**  
   Redis is already deployed, monitored, and operated by the current team. Adding Redis Streams requires no new infrastructure, no new deployment artifacts, and no new operational runbooks. By contrast, self-hosting Kafka (even KRaft mode) introduces broker provisioning, partition rebalancing, replication tuning, and distinct failure modes that are hazardous for a team without dedicated platform engineering.

2. **Time-to-value within the two-week constraint**  
   A Redis Streams consumer group (`XREADGROUP` / `XACK`) can be prototyped in days and moved to production inside the migration window. Kafka would require learning producer/consumer semantics, exactly-once transaction configuration, and broker-level tuning before shipping a single retry — a realistic timeline of 4–6 weeks for a team with no prior experience.

3. **Sufficient throughput headroom for 10× growth**  
   Redis Streams routinely sustains **>100,000 messages/second per node**. Our peak of ~500 req/s translates to roughly a few thousand notification messages per second at most; 10× growth still sits two orders of magnitude below Redis saturation, giving ample runway without re-architecting.

4. **Ordering and consumer-group semantics meet our requirements**  
   Redis Streams provides FIFO ordering within a single stream and supports consumer groups with automatic message claiming (`XPENDING` / `XCLAIM`). This gives us the at-least-once backbone and retry mechanics we need. Billing events will be routed to a dedicated stream to isolate ordering from high-volume webhook traffic.

5. **Exactly-once for billing notifications via application-level idempotency**  
   Redis Streams is fundamentally an at-least-once system. To satisfy the exactly-once requirement for billing events, consumers will persist processed event IDs in the existing PostgreSQL database using an atomic "insert-or-ignore" idempotency table. This pattern is well understood, leverages an already-trusted data store, and avoids the distributed-transaction complexity of Kafka transactions.

6. **Natural synergy with future WebSocket real-time pushes**  
   Because Redis is already the shared state layer, we can reuse Redis Pub/Sub (alongside Streams) for the upcoming WebSocket notification feature without introducing a second messaging technology.

## Consequences

### Pros

- **Low operational burden**: Single technology already in production; no additional AWS resources or monitoring stacks.
- **Fast migration**: Can move synchronous notification code to async workers in under two weeks.
- **Adequate performance**: More than enough throughput for current and projected loads.
- **Unified infrastructure**: Future WebSocket push can reuse the same Redis cluster.
- **Consumer-group recovery**: Built-in `XPENDING` and `XCLAIM` make it straightforward to reprocess failed messages after a consumer crash.

### Cons

- **Exactly-once is application-managed**: If the idempotency table is bypassed or misconfigured, billing events could be duplicated. This shifts correctness responsibility from the infrastructure to the application code.
- **Retention is memory-bound**: Streams must be trimmed (e.g., `MAXLEN` or `MINID`) to prevent unbounded memory growth. We must size the cluster to retain at least 24–48 hours of events and back up to S3 if longer audit retention is required.
- **Weaker durability than replicated log storage**: Redis AOF provides durability, but it is not as robust as Kafka’s replicated, immutable log. A catastrophic, simultaneous failure of the primary and snapshot could lose un-trimmed stream data.
- **Manual partitioning for extreme scale**: If we eventually outgrow a single Redis primary, sharding streams across nodes is manual. (This is not expected within the current growth horizon.)

## Alternatives Considered

### Apache Kafka

Kafka was rejected for this phase because its strengths do not outweigh the constraints of the team and timeline.

- **Operational complexity**: Even with KRaft (ZooKeeper-less) mode, a production Kafka cluster requires broker sizing, partition strategy design, replication-factor decisions, and careful consumer-group rebalancing. Without a dedicated infrastructure engineer, this operational load is disproportionate to the team size.
- **Experience gap**: The team has no prior Kafka expertise. Learning producer idempotency, transactional semantics, and operational troubleshooting would push a production-ready deployment well beyond the two-week window.
- **Cost**: Managed options (Confluent Cloud, AWS MSK) exceed the modest budget. Self-hosting on EC2 saves money but amplifies the operational burden already flagged as a risk.
- **Overkill for current scale**: Kafka shines at millions of messages per second and multi-petabyte retention. Our notification volume is orders of magnitude smaller; we would be paying complexity tax for headroom we do not yet need.

Kafka remains a candidate for future evaluation if the team grows, operational expertise is hired, or notification volume crosses the threshold where Redis vertical scaling becomes impractical.
