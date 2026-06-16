# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is implemented synchronously within the Flask HTTP request cycle. This has led to significant production issues:
- **Performance Degradation**: Response times spike up to 8s during peak hours (500 req/s) due to blocking I/O.
- **Reliability Gaps**: No retry mechanisms or Dead Letter Queues (DLQ), resulting in silent failures when downstream providers (email/webhooks) are unavailable.
- **Stability Risks**: Slow webhook endpoints cause connection pool exhaustion, leading to cascading failures across the platform.
- **Consistency Issues**: Lack of delivery guarantees for billing-critical notifications.

**Constraints:**
- Small team (6 engineers), no dedicated DevOps/Infra resource.
- Existing production dependency on Redis.
- Zero internal expertise in Apache Kafka.
- Tight timeline: Value must be delivered within 2 weeks.
- Budget constraints preventing high-cost managed Kafka services.
- Target: 10x growth (5k req/s) and future WebSocket integration.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Redis Streams provides a pragmatic balance between the required technical guarantees and the team's operational capacity. Given that Redis is already in production, the operational overhead is near zero. It satisfies the requirement for async decoupling, consumer groups for scaling, and persistent message logs for retries.

## Consequences

### Pros
- **Operational Simplicity**: No new infrastructure to deploy, monitor, or patch. The team can leverage existing Redis knowledge.
- **Rapid Time-to-Value**: Implementation can be completed within the 2-week window using existing infrastructure.
- **Performance**: Extremely low latency for both producers (web servers) and consumers, comfortably handling the current 500 req/s and the 10x growth target.
- **Consumer Groups**: Support for `XGROUP` allows us to distribute notifications across multiple worker processes for parallel processing and fault tolerance.
- **Real-time Readiness**: Seamlessly integrates with the planned WebSocket push notifications, as Redis is already a standard choice for Pub/Sub and state management for WebSockets.

### Cons
- **Memory Constraints**: Unlike Kafka's disk-based storage, Redis is primarily in-memory. We will need to implement aggressive `XTRIM` policies (e.g., `MAXLEN`) to prevent OOM errors as volume grows.
- **Lower Durability Guarantees**: While AOF/RDB provides persistence, it is not as robust as Kafka's distributed commit log. We accept this risk for notifications, mitigated by the fact that billing events can be re-driven from the PostgreSQL source of truth if a catastrophic Redis failure occurs.

## Alternatives Considered

### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity**: Kafka requires Zookeeper (or KRaft) and significant tuning for JVM, disk I/O, and networking. With no dedicated infra engineer, the "day 2" operational burden is too high.
- **Learning Curve**: The team has zero Kafka experience. The time spent learning the API and operational nuances would exceed the 2-week delivery constraint.
- **Cost**: Self-hosting requires dedicated nodes; managed services (Confluent) are currently outside the modest budget.
- **Overkill**: While Kafka offers superior "Exactly-Once" semantics (via transactional producers), Redis Streams combined with idempotent consumer logic (tracking processed IDs in Postgres) is sufficient for our billing-critical events.

## Final Comparison Matrix

| Feature | Redis Streams | Apache Kafka | Selection Logic |
| :--- | :--- | :--- | :--- |
| **Ops Overhead** | Very Low (Existing) | High (New Stack) | Redis wins on team size/skills |
| **Throughput** | High (In-memory) | Ultra High (Disk-sequential) | Both meet 10x growth target |
| **Ordering** | Guaranteed per stream | Guaranteed per partition | Both satisfy requirements |
| **Retention** | Memory-bound (Trimmed) | Disk-bound (Configurable) | Redis sufficient for short-term logs |
| **Setup Time** | < 1 day | Weeks | Redis meets 2-week constraint |
| **Exactly-Once** | App-level (Idempotency) | Native (Transactions) | Redis + Postgres is sufficient |
