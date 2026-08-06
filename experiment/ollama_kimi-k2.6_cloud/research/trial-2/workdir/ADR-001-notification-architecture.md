# ADR-001 — Notification Subsystem Architecture

## Status

Proposed

## Context

The notifications module in our SaaS project management platform currently sends emails and webhooks synchronously inside the HTTP request cycle. As the platform has grown to 85,000 monthly active users and ~2M tasks created per month, this design has become a critical bottleneck and reliability risk.

Current symptoms:

- **Request timeouts**: Notification I/O blocks HTTP responses. Average latency is 800ms, with spikes to 8 seconds during peak hours (~500 req/s).
- **Silent failures**: If an email provider or webhook endpoint is unavailable, the notification is dropped with no retry mechanism or dead-letter queue.
- **Cascading failures**: Two incidents this year occurred when a slow webhook endpoint caused connection pool exhaustion in the Python/Flask monolith, degrading unrelated features.
- **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") must be delivered exactly once, but the current system provides no such guarantee.

We need to decouple notification delivery from the HTTP request cycle, introduce retry with exponential backoff, and guarantee at-least-once delivery for all notifications, with exactly-once semantics for billing events. Within two quarters, we also plan to add real-time WebSocket push notifications. The solution must support 10x traffic growth without a wholesale re-architecture.

### Constraints

- **Engineering team**: 6 people (3 senior, 3 mid-level), with no dedicated infrastructure engineer.
- **Existing infrastructure**: Redis is already in production (session storage, rate limiting). PostgreSQL and AWS are the data and compute platforms.
- **Experience gap**: No engineer on the team has production experience operating Apache Kafka.
- **Timeline**: Maximum of two weeks for setup and migration before the new queue must deliver production value.
- **Budget**: Modest. Managed Confluent Cloud or a large MSK deployment is not affordable at current scale.

## Decision

We will use **Redis Streams** as the message queue for the notification subsystem.

Redis Streams provides the durability, consumer-group semantics, and message retention needed to move notification processing out of the HTTP request path. By building idempotent consumers on top of Redis Streams—using PostgreSQL unique constraints on message IDs to deduplicate billing events—we can satisfy the exactly-once requirement for billing notifications without introducing a new infrastructure tier. The migration can be completed incrementally against the existing Redis instance, keeping the two-week deadline achievable.

## Consequences

### Positive

- **Rapid deployment**: Redis Streams is a data structure, not a new service. We can begin producing and consuming messages within days by extending the Redis instance already running in production, avoiding provisioning, networking, and security reviews for new infrastructure.
- **Low operational overhead**: The team already operates Redis for sessions and rate limiting. Monitoring, failover, and backup procedures are in place. Adding Streams does not increase the operational surface area the way adding Kafka brokers, ZooKeeper/KRaft nodes, and topic-partition management would.
- **Fits team constraints**: With no dedicated infrastructure engineer and no Kafka experience, self-hosting Kafka would carry an unacceptable risk of misconfiguration and on-call burden. Redis Streams lets the team focus on application-level reliability (retry logic, idempotency, circuit breakers) rather than distributed stream platform operations.
- **Sufficient headroom for growth**: At peak, the system sees ~500 req/s. Redis Streams with consumer groups can comfortably handle an order of magnitude beyond that on a single node. If sustained throughput eventually exceeds a single Redis node, Redis Cluster provides a horizontal path without changing the queue semantics.
- **Natural WebSocket integration**: Redis is already used for real-time patterns. The planned WebSocket push feature can reuse the same Redis infrastructure (Pub/Sub or additional Streams) within the two-quarter window, avoiding a second messaging technology.

### Negative

- **Exactly-once is application-level**: Redis Streams provides at-least-once delivery. Guaranteeing exactly-once processing for billing notifications requires careful consumer design—specifically, persisting a processed-message ID to PostgreSQL with a unique constraint before acknowledging the message in Redis. A bug in this idempotency logic could lead to duplicate billing events.
- **Memory-bound retention**: Message retention is constrained by available memory unless we offload to disk-tier products (not in use today). We must size the instance and configure trimming policies (e.g., `MAXLEN` or time-based eviction) to prevent unbounded growth.
- **Scaling ceiling**: While Redis Streams handles 10x growth, extreme scale (tens of thousands of messages per second sustained with long retention) would eventually favor a partitioned log architecture like Kafka. We accept this trade-off because our projected growth and retention needs do not approach that ceiling within the current planning horizon.
- **Ecosystem maturity**: Kafka offers richer stream-processing primitives (e.g., Kafka Streams, Kafka Connect, schema evolution). We will build retry, backoff, and dead-letter logic in application code rather than using off-the-shelf stream-processing frameworks.

## Alternatives Considered

### Apache Kafka

Kafka is the strongest alternative on technical merit alone. It is purpose-built for high-throughput, partitioned, durable event streaming and offers first-class exactly-once semantics via idempotent producers and transactional consumers. Its consumer-group model, retention policies, and ordering guarantees within partitions are superior to Redis Streams for large-scale stream processing.

We rejected Kafka because:

- **Operational complexity exceeds team capacity**: A production Kafka deployment requires broker provisioning, partition sizing, replication-factor tuning, consumer-lag monitoring, and rebalancing management. Without a dedicated infrastructure engineer, this operational burden introduces a high risk of incidents and pager fatigue.
- **Timeline risk**: Setting up a self-hosted Kafka cluster on AWS, establishing production runbooks, and migrating notification logic with correct offset management and failure modes is unlikely to be completed and battle-tested within the two-week constraint by a team with no prior Kafka experience.
- **Budget constraint**: Managed options such as Confluent Cloud or MSK exceed our modest budget at the throughput levels required for 10x growth. Self-hosting on EC2 reduces cost but amplifies the operational complexity problem.
- **Overkill for current scale**: At 500 req/s peak, Kafka's throughput advantages are not exercised. The primary pain points are reliability and decoupling, not raw throughput. Redis Streams addresses these pain points immediately without the overhead of a second distributed system.

We would revisit Kafka if the team hires dedicated infrastructure staff, if message volume consistently exceeds what a Redis Cluster can sustainably retain and serve, or if we require advanced stream-processing primitives (e.g., event-time windowing, stream-table joins) that justify the operational investment.
