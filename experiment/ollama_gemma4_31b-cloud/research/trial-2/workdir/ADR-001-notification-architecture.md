# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

## Context
Our current notification system is synchronous, leading to request timeouts (up to 8s), silent failures during provider downtime, and cascading failures that exhaust connection pools. We need a decoupled, asynchronous architecture that supports:
- **Reliability**: Retries with exponential backoff and delivery guarantees.
- **Scalability**: Ability to handle 10x current peak traffic (~5,000 req/s).
- **Future-proofing**: Support for real-time WebSocket push notifications.
- **Constraints**: A small team (6 engineers) with no dedicated infra engineer, no Kafka experience, and a modest budget. We already operate Redis in production. Delivery of value must begin within two weeks.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Given the current constraints, the operational overhead of Kafka is prohibitive. Redis Streams provides a sufficient primitive for our scaling targets while leveraging our existing infrastructure and team familiarity.

1. **Operational Simplicity**: We already run Redis. Deploying Streams requires zero new infrastructure components, fitting the <2-week delivery window. Kafka would require a new cluster, Zookeeper/KRaft management, and a learning curve for the entire team.
2. **Performance**: Redis Streams can easily handle our 10x target (5k req/s) with sub-millisecond latency, as it operates primarily in-memory.
3. **Consumer Groups**: Redis Streams supports Consumer Groups (similar to Kafka), allowing us to distribute notification processing across multiple workers and track offsets.
4. **Message Retention**: While Redis is not a permanent log like Kafka, we can use `XADD` with `MAXLEN` to maintain a rolling buffer of messages sufficient for our retry windows.
5. **Delivery Guarantees**: By utilizing Consumer Group Acknowledgments (`XACK`) and Pending Entries Lists (`XPENDING`), we can implement at-least-once delivery. For billing-critical "exactly-once" requirements, we will implement an **Idempotency Key** pattern in the consumer (backed by PostgreSQL), as neither system provides true exactly-once semantics without external state coordination.

## Consequences
**Pros:**
- **Near-zero setup time**: Immediate start on implementation.
- **Low cognitive load**: The team uses a tool they already know.
- **Cost-efficient**: No additional licensing or expensive managed cluster fees.
- **WebSocket Ready**: The transition to real-time push notifications is seamless, as Redis is already the industry standard for Pub/Sub and WebSocket state management.

**Cons:**
- **Memory Constraints**: Message retention is limited by available RAM. We must be disciplined with `MAXLEN` and avoid treating Redis as a long-term archive.
- **Persistence Risks**: While AOF/RDB provide durability, Kafka's disk-first approach is inherently more robust for massive data retention.

## Alternatives Considered
**Apache Kafka**
Rejected. While Kafka is the gold standard for high-throughput event streaming and offers superior long-term retention and "exactly-once" semantics via transactional producers, it is overkill for our current scale (~500-5,000 req/s). The operational complexity of managing a Kafka cluster without a dedicated infra engineer would likely lead to the same "cascading failure" risks we are currently trying to solve. The time-to-value would exceed the two-week constraint.
