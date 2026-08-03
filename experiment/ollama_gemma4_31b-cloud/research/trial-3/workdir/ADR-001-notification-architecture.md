# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to request timeouts (up to 8s), silent failures, and cascading failures that impact system stability. We need to decouple notifications from the HTTP request cycle to support:
- Async processing with exponential backoff retries.
- At-least-once delivery for billing-critical events.
- Exactly-once semantics for billing notifications.
- Support for 10x traffic growth (~5,000 req/s peak).
- Future integration of real-time WebSocket push notifications.

**Constraints:**
- Team size: 6 engineers (no dedicated infra specialist).
- Existing infra: AWS, Redis (used for sessions/rate limiting).
- Experience: No Kafka experience on the team.
- Timeline: Max 2 weeks for setup/migration to deliver initial value.
- Budget: Modest; managed Kafka (Confluent) is too expensive.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Operational Simplicity**: We already run Redis in production. Leveraging an existing tool eliminates the "Day 1" infrastructure setup cost and the "Day 2" operational burden of managing a Zookeeper/Kafka cluster or paying for a high-cost managed service.
2. **Time-to-Value**: Given the 2-week constraint, Redis Streams can be implemented immediately using existing client libraries. Kafka's steep learning curve for a team with zero experience would jeopardize the delivery timeline.
3. **Performance**: Redis Streams easily handle our 10x growth target (~5,000 req/s). With typical notification payloads, Redis's in-memory throughput is more than sufficient.
4. **Consumer Groups**: Redis Streams provide consumer group support (XGROUP), enabling the same scalable, distributed processing model as Kafka (competing consumers, offset tracking).
5. **Billing Guarantees**: By combining Redis Streams (at-least-once) with **idempotency keys** in the PostgreSQL database for billing events, we achieve the required exactly-once semantics without the extreme complexity of Kafka's transactional producers.

## Consequences
**Pros:**
- **Low Overhead**: Zero new infrastructure components to deploy or monitor.
- **Rapid Deployment**: Team can focus on the application logic (retries, DLQs) rather than cluster tuning.
- **Resource Efficiency**: Shared memory usage with existing Redis instances (provided we monitor memory pressure).
- **Future-Ready**: Redis Pub/Sub or Streams integrate naturally with the planned WebSocket push notifications.

**Cons:**
- **Persistence Trade-off**: Redis is primarily in-memory. While AOF (Append Only File) provides durability, it is not as robust as Kafka's distributed commit log for long-term retention.
- **Retention Management**: We must implement active trimming (`XTRIM`) to prevent Redis from running out of memory as message volume grows.
- **Scaling Ceiling**: While sufficient for 5,000 req/s, Redis is vertically scalable. If we eventually hit millions of events per second, we would need to move to a distributed log like Kafka.

## Alternatives Considered
**Apache Kafka**
Rejected for the following reasons:
- **Operational Complexity**: Managing a Kafka cluster requires specialized knowledge (partitions, replication factors, Zookeeper/KRaft) that the team currently lacks.
- **Cost**: A self-managed cluster adds significant AWS EBS and compute overhead; a managed service (Confluent) exceeds the current budget.
- **Overkill**: Kafka's primary strengths (massive throughput, long-term replayable storage) are not requirements for this system. The 10x growth target is well within Redis's capabilities.
- **Implementation Time**: The time required to learn, configure, and verify Kafka would exceed the 2-week window for delivering initial value.
