# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing request timeouts (spikes up to 8s), silent failures of emails/webhooks, and cascading failures due to connection pool exhaustion. We require a decoupled, asynchronous architecture to support:
- Reliable delivery with exponential backoff retries.
- At-least-once delivery for all notifications; exactly-once for billing-critical events.
- Scaling to 10x current traffic (~5,000 req/s peak).
- Future support for real-time WebSocket push notifications.

**Constraints:**
- Team: 6 engineers (no dedicated infra engineer).
- Current Stack: Python/Flask, PostgreSQL, Redis (already in production).
- Zero Kafka experience on the team.
- Strict time-to-value requirement: < 2 weeks for initial setup/migration.
- Modest budget (managed Kafka is cost-prohibitive).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Operational Complexity & Team Skillset**: The team already manages Redis in production. Introducing Kafka would require learning a complex new ecosystem (ZooKeeper/KRaft, JVM tuning, partition management) with no dedicated infra support. Redis Streams provides a familiar mental model with negligible setup time, fitting the < 2-week delivery constraint.
2. **Throughput & Latency**: At 5,000 req/s peak, Redis Streams easily meets performance requirements. While Kafka scales higher, Redis is more than sufficient for this order of magnitude.
3. **Consumer Groups**: Redis Streams supports Consumer Groups (`XGROUP`), providing the necessary ability to distribute notification processing across multiple workers and track message acknowledgement (ACK), enabling reliable at-least-once delivery.
4. **Exactly-Once Semantics**: While neither provides global exactly-once without coordination, we will implement **idempotent consumers** using the existing PostgreSQL database. By storing a `notification_id` in a processed_notifications table, we achieve the required exactly-once semantics for billing events regardless of the transport layer.
5. **Integration**: Redis is already used for sessions/rate-limiting; adding Streams leverages existing infrastructure without increasing the architectural surface area.

## Consequences
**Pros:**
- **Immediate Velocity**: Zero new infrastructure to provision; minimal learning curve for the team.
- **Low Overhead**: Extremely low latency and high throughput for the current and target scale.
- **Reliability**: Consumer groups and PEL (Pending Entries List) allow for robust retry logic and recovery from worker crashes.
- **Cost Effective**: No additional licensing or expensive managed service costs.

**Cons:**
- **Retention Limits**: Unlike Kafka's long-term disk-based retention, Redis is primarily in-memory. We must implement a strategy to prune streams (`XTRIM`) to avoid OOM, though the 10x growth target is still well within Redis's memory capabilities.
- **Lower Maximum Ceiling**: While sufficient for 10x growth, it does not scale to the millions of messages per second that Kafka handles. However, this is a premature optimization given the current 500 req/s baseline.

## Alternatives Considered
**Apache Kafka**
- **Reason for Rejection**: The operational burden is too high for a 6-person team without infra expertise. The "cold start" time to properly configure, deploy, and monitor a production-grade Kafka cluster would exceed the 2-week constraint. The complexity of managing partitions and offsets outweighs the benefits of Kafka's superior durability and throughput, which are not required at our current scale.
