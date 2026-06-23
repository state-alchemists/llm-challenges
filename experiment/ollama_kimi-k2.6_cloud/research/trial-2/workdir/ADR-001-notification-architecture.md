# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform processes ~2M tasks per month across 85,000 monthly active users, with peak HTTP traffic of ~500 req/s. Today, notifications (emails and webhooks) are handled synchronously inside the Flask request cycle. This has produced four concrete problems:

1. **Request timeouts**: Average notification latency is 800ms, spiking to 8s during peak hours because sending blocks the HTTP response.
2. **Silent failures**: No retry mechanism exists; if an email provider or webhook endpoint is down, the notification is dropped.
3. **Cascading failures**: Two incidents this year saw a slow webhook endpoint exhaust the application connection pool, degrading unrelated features.
4. **No delivery guarantees**: Billing-critical events (e.g., "trial expired", "payment failed") must be delivered exactly once, but the current system cannot provide even at-least-once semantics.

We must decouple notification processing from the HTTP request path, introduce retry with exponential backoff, and guarantee delivery. Within two quarters we also need to add real-time WebSocket push notifications. The solution should support 10x traffic growth (5,000 req/s peak, ~20M tasks/month) without forcing a future re-architecture.

**Team and infrastructure constraints:**

- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- We already run Redis in production for sessions and rate limiting.
- No team member has production Kafka experience.
- Migration must deliver value within 2 weeks.
- Budget is modest; managed Confluent Cloud is not viable at scale today.
- Exactly-once semantics are required for billing notifications.

## Decision

We will adopt **Redis Streams** as the backbone of the notification subsystem.

**Justification**

Redis Streams satisfies the immediate requirements while respecting the team's operational reality. At our current scale (~2M tasks/month, 500 req/s peak, with a target of 10x), a single Redis node can comfortably handle the throughput. Redis Streams offers:

- **Sufficient throughput**: A single Redis node can process 500K+ messages/second; our 10x target of ~5,000 req/s peak is well within bounds.
- **Ordered delivery within a stream**: Each consumer group reads entries in insertion order, which satisfies our need for sequential task-update processing per user or per project.
- **Consumer groups and horizontal scaling**: Multiple Python worker processes can join a consumer group (`XREADGROUP`) and split partitions across instances. Redis automatically handles ownership with `XPENDING` and `XCLAIM`, giving us retry and dead-letter semantics without additional infrastructure.
- **Bounded operational complexity**: We already operate Redis for sessions and rate limiting. Adding Streams uses the same tooling, monitoring, and runbooks. There is no new deployment artifact to learn, secure, or tune.
- **2-week feasibility**: Streams is a data structure, not a separate product. We can introduce it by pointing our existing Redis client to a new keyspace, deploying workers, and migrating one notification type at a time. This fits the 2-week constraint.
- **Exactly-once for billing**: Redis Streams does not provide native exactly-once semantics. We will implement application-level idempotency: each billing event carries a unique `event_id` (UUID v4), and consumers write a deduplication record into PostgreSQL (`INSERT INTO processed_events ... ON CONFLICT DO NOTHING`) before performing the side effect. This pattern is well understood, adds minimal latency, and leverages a database we already run.
- **WebSocket alignment**: Our Q3 goal of real-time WebSocket push maps cleanly to Redis. Streams can feed a lightweight pub/sub layer (or the same Redis instance) that pushes updates to WebSocket servers without introducing a second message bus.

Kafka is technically superior for massive-scale, long-term log storage and native exactly-once processing. However, self-hosting Kafka (ZooKeeper or KRaft, partition rebalancing, consumer group coordination, broker tuning) would consume most of the 2-week window just for setup, and ongoing operational burden would fall on a team with no Kafka expertise and no dedicated SRE. The risk of a misconfigured cluster causing an incident outweighs the future throughput benefits at our current and near-future scale.

## Consequences

### Pros

- **Fast time to value**: Can be running in production inside days, not weeks.
- **Low operational risk**: Uses existing Redis infrastructure, monitoring, and team expertise.
- **No new hosting costs**: Runs on the Redis instances we already pay for; memory growth can be managed with capped stream lengths (`MAXLEN`) and longer-term archival to S3 if needed.
- **Natural path to WebSocket**: Same data store can power real-time push in Q3.
- **Consumer-group primitives**: Built-in `XPENDING`, `XCLAIM`, and `XDEL` give us retry, dead-letter, and acknowledgment semantics without extra services.

### Cons

- **Memory-bound retention**: Redis is an in-memory store. Deep historical replay (e.g., reprocessing the last 30 days of events) is expensive. We will mitigate this by archiving completed notification events to S3 after 7 days and enforcing `MAXLEN` on live streams.
- **No native exactly-once**: Requires application-level idempotency via PostgreSQL deduplication tables. This adds a small amount of latency (~5–10ms) and must be implemented correctly in every consumer.
- **Single-node bottleneck at extreme scale**: While 10x growth fits comfortably in a single Redis node, 100x growth would eventually require Redis Cluster or a migration to Kafka. We accept this trade-off because 100x is not on the near-term roadmap, and Cluster is a well-documented upgrade path if needed.
- **Weaker ecosystem**: Kafka has richer connectors, stream-processing frameworks (Kafka Streams, ksqlDB), and mature exactly-once abstractions. We will build simpler Python workers instead; this is acceptable for a notification pipeline that does not require complex joins or windowed aggregations.

## Alternatives Considered

### Apache Kafka

We rejected self-hosted Apache Kafka for this phase.

- **Operational complexity**: A production Kafka deployment requires managing brokers, partition counts, replication factors, consumer group rebalances, and either ZooKeeper or KRaft metadata nodes. Our 6-person team has no production experience with these components, and mistakes in configuration have caused data loss and availability incidents in similar small-team environments.
- **Setup time**: Even a minimal 3-broker cluster with proper monitoring and topic provisioning would consume the majority of the 2-week migration window before delivering user-facing value.
- **Cost of managed options**: Confluent Cloud or MSK would remove operational burden but exceed our modest budget at the 10x traffic target.
- **Overkill for current scale**: Kafka shines at millions of events per second with long retention requirements. Our peak is 500 req/s and our retention need is measured in days, not years. Redis Streams provides the same core primitives (ordered log, consumer groups, replay) at a fraction of the operational cost for our volume.

Kafka remains the likely long-term destination if we grow beyond what Redis Cluster can handle, but it is the wrong tool for the team's size, skill set, and 2-week deadline today.
