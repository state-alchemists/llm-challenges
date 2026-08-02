# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform currently handles notifications (emails, webhooks) synchronously inside the HTTP request cycle. At 85,000 monthly active users and peak loads of ~500 req/s, this has produced four critical failure modes:

1. **Request timeouts**: Notifications block HTTP responses; average latency is 800ms with spikes to 8s.
2. **Silent failures**: Downstream providers or webhook endpoints cause dropped messages with no retry mechanism.
3. **Cascading failures**: Slow webhook endpoints have exhausted connection pools and taken down unrelated features.
4. **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") can be lost or duplicated.

We need an asynchronous message-streaming layer that decouples notification submission from delivery, supports retry with exponential backoff, guarantees at-least-once delivery for general events, and provides exactly-once delivery for billing events. Within two quarters we also intend to add real-time WebSocket push notifications. The solution must support 10x traffic growth (to ~5,000 req/s peak) without requiring a future re-architecture.

Our constraints are:
- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- **Timeline**: Must deliver value within 2 weeks.
- **Budget**: Modest; managed Kafka (Confluent Cloud) at full scale is not affordable today.
- **Existing infrastructure**: Redis is already in production (session storage, rate limiting), but no team member has production Kafka experience.

## Decision

We will adopt **Redis Streams** as the backbone of the new notification subsystem.

### Justification

While Apache Kafka is architecturally superior for extreme-scale, long-retention stream processing, the operational cost of introducing it given our team size, budget, and timeline outweighs its marginal technical benefits for our present scale. Redis Streams provides sufficient throughput, consumer-group semantics, and persistence for our needs, and because Redis is already operational, we can meet the 2-week delivery window without adding new infrastructure to manage.

Key technical considerations:

- **Throughput**: Redis Streams can sustain tens of thousands of messages per second per node. Our peak is 500 req/s today and our 10x target is ~5,000 req/s, which is well within Redis Streams' capacity on our existing instance class.
- **Ordering guarantees**: Redis Streams provides ordered, append-only logs per stream. Partitioning by event type (e.g., `stream:billing`, `stream:email`, `stream:webhook`) preserves ordering within each category, which satisfies our requirement.
- **Message retention**: Streams support a `MAXLEN` cap, and Redis 6+ supports automatic trimming. For our use case notifications are ephemeral. We will retain messages for 7 days, which provides ample time for consumer replay and debugging without imposing unbounded memory growth.
- **Consumer groups**: Redis Streams implements consumer groups with explicit `XREADGROUP` / `XACK` semantics. If a worker crashes, unacknowledged messages remain pending and can be claimed by another consumer via `XPENDING` / `XCLAIM`, enabling at-least-once delivery.
- **Exactly-once semantics**: Neither Kafka nor Redis Streams provides true exactly-once delivery without application-layer cooperation. We will implement client-side idempotency by storing processed billing-event IDs in PostgreSQL with a unique constraint. This pattern is simpler to operationalize with Redis Streams because we avoid the additional complexity of Kafka transactional producers and consumer-group rebalancing.
- **Operational complexity**: Kafka (even KRaft mode) requires partition planning, broker monitoring, replication tuning, and careful consumer rebalancing. Without a dedicated infrastructure engineer, this introduces unacceptable risk. Redis Streams runs on our existing Redis deployment; our team already knows how to monitor, back up, and failover Redis.
- **Migration / setup**: Because Redis is already in production, enabling Streams requires zero new infrastructure. We can begin migrating notification producers and consumers within days, confidently meeting the 2-week constraint.
- **Future WebSocket support**: Redis Pub/Sub is the standard mechanism for broadcasting WebSocket messages in Python/Flask ecosystems. Reusing Redis for Streams and Pub/Sub keeps our real-time stack unified.

## Consequences

### Pros
- **Fast time to value**: Existing Redis infrastructure means no procurement, provisioning, or networking work. We can start building producers and consumers immediately.
- **Lower operations burden**: The team does not need to learn Kafka operations (broker tuning, partition rebalancing, consumer lag semantics) or run additional JVM-based services.
- **Unified infrastructure**: Redis will serve cache, sessions, rate limiting, streaming, and WebSocket broadcasting. One operational model reduces cognitive load.
- **Sufficient headroom**: ~5,000 msg/s peak is comfortably inside Redis Streams' performance envelope on modern AWS ElastiCache or EC2 instance types.
- **Explicit acknowledgment model**: `XACK` and `XCLAIM` give us fine-grained control over retry and dead-letter behavior.

### Cons
- **Less durable than Kafka**: Redis is memory-oriented. Although AOF and RDB persistence mitigate data loss on restart, a catastrophic failure without persistence could lose unprocessed stream data. We will mitigate this by enabling AOF `everysec` and treating uncommitted stream messages as durable only after consumer acknowledgment.
- **Retention is size-bound, not time-bound by default**: We must configure stream caps explicitly (`MAXLEN` or `MINID`) to prevent memory exhaustion. We will automate this with a scheduled trimming job.
- **Smaller ecosystem**: There are fewer ready-made stream-processing libraries for Redis Streams compared to Kafka (e.g., Kafka Streams, ksqlDB). We will build lightweight Python workers rather than adopting a heavy framework.
- **Application-level exactly-once**: We lack Kafka's native idempotent producer and transactional consumer support. Our PostgreSQL idempotency table introduces a small latency overhead and requires maintenance, but it is a simpler failure mode than misconfigured Kafka transactions.
- **Scaling ceiling**: If we grow far beyond 10x and need cross-region replication or petabyte-scale retention, we may need to migrate to Kafka. At that point we will likely have the resources to hire infrastructure expertise.

## Alternatives Considered

### Apache Kafka

We rejected **self-hosted Apache Kafka** for this phase.

Kafka offers stronger durability, longer retention, native exactly-once semantics via idempotent producers and transactional consumers, and a mature ecosystem of connectors and stream processors. For a very large organization with dedicated SREs and multi-year data-retention requirements, Kafka is the superior choice.

However, for our specific constraints, Kafka is the wrong tool at the wrong time:

1. **Setup timeline**: Deploying a production-grade Kafka cluster (3+ brokers, ZooKeeper or KRaft controllers, monitoring, alerting) and migrating the notification pipeline in under 2 weeks is unrealistic for a team with zero Kafka experience.
2. **Operational complexity**: Without a dedicated infrastructure engineer, the team would be on-call for broker failures, partition rebalancing events, and consumer-group coordinator issues. Our operational surface area is already constrained.
3. **Budget**: Managed Kafka (Confluent Cloud, MSK) is cost-prohibitive at our modest budget. Self-hosted shifts the cost to engineering time we do not have.
4. **Overkill for throughput**: Our 10x target (~5,000 msg/s) is well below the threshold where Kafka's partitioning and replication model become necessary. Redis Streams handles this comfortably on a single primary with a read replica.
5. **Exactly-once complexity**: Kafka's exactly-once semantics require transactional producer configuration, isolation levels, and consumer-side transactional offsets. Implementing this correctly in Python/Flask is non-trivial and error-prone. The application-level idempotency approach with Redis Streams is simpler to verify and maintain for a 6-person team.

**Verdict**: Kafka will be re-evaluated if we outgrow Redis Streams' operational envelope (likely past 50,000 msg/s or when multi-region retention becomes a hard requirement). For the current maturity and scale of our platform, Redis Streams is the pragmatic, responsible choice.
