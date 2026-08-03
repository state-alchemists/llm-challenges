# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, blocking the HTTP request cycle and causing request timeouts (up to 8s) and cascading failures. We lack delivery guarantees for billing-critical notifications and have no retry mechanism for failed webhooks or emails.

**Constraints:**
- **Team Size**: 6 engineers; no dedicated infrastructure/DevOps engineer.
- **Existing Stack**: Python/Flask, PostgreSQL, Redis (already in production).
- **Experience**: Team has zero experience with Apache Kafka.
- **Timeframe**: Must deliver value within 2 weeks.
- **Scale**: 500 req/s peak; target 10x growth (5,000 req/s).
- **Requirements**: At-least-once delivery for general notifications; exactly-once semantics for billing events; support for future WebSocket push notifications.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Given the team's current composition and infrastructure, Redis Streams provides the optimal balance of performance and operational simplicity. Since Redis is already running in production for session storage and rate limiting, the marginal operational overhead is nearly zero.

Redis Streams satisfies the core technical requirements:
- **Throughput**: Easily handles the current 500 req/s and the projected 5,000 req/s target.
- **Consumer Groups**: Provides the necessary mechanism for distributed processing and tracking which messages have been acknowledged.
- **Ordering**: Guarantees strict ordering within a stream.
- **Operational Complexity**: No new infrastructure to deploy, monitor, or secure. The team can leverage existing Redis knowledge.
- **Delivery Guarantees**: Combined with consumer group acknowledgments (`XACK`) and pending entries lists (`XPENDING`), we can implement at-least-once delivery. For exactly-once billing notifications, we will implement an idempotent consumer pattern using the existing PostgreSQL database to track processed event IDs.

## Consequences
### Pros
- **Zero New Infrastructure**: No additional servers, JVMs, or ZooKeeper/KRaft clusters to manage.
- **Rapid Deployment**: The 2-week setup window is easily met as the tool is already installed.
- **Low Latency**: Sub-millisecond overhead for appending events to the stream.
- **Simplified Tooling**: Use existing Redis monitoring and backup strategies.

### Cons
- **Memory Bound**: Redis is an in-memory store. While we can cap stream length (`MAXLEN`), long-term retention for audit logs would require archiving to PostgreSQL.
- **Lower Durability than Kafka**: While AOF/RDB provide persistence, they are generally less robust than Kafka's distributed commit log for catastrophic failure scenarios. However, for a notification system, this is an acceptable trade-off.

## Alternatives Considered
**Apache Kafka**
We rejected Kafka for the following reasons:
- **Operational Overhead**: Kafka requires significant expertise to manage (brokers, partitions, coordination). With no dedicated infra engineer and zero team experience, the risk of misconfiguration causing production outages is high.
- **Resource Heavy**: The JVM footprint and infrastructure requirements are excessive for the current scale and budget.
- **Implementation Timeline**: Setting up a production-ready Kafka cluster and integrating it would likely exceed the 2-week deadline for delivering initial value.
- **Over-engineering**: While Kafka offers superior throughput and long-term retention, the 10x growth target (5k req/s) is well within the capabilities of a well-tuned Redis Streams implementation.
