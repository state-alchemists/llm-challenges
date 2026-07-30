# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current synchronous notification system is causing request timeouts (up to 8s), silent failures, and cascading system crashes due to connection pool exhaustion. We need to decouple notifications from the HTTP request cycle to improve stability and support 10x growth.

### Constraints
- **Team**: 6 engineers (no dedicated infra/DevOps).
- **Existing Stack**: Python/Flask, PostgreSQL, AWS, Redis.
- **Knowledge**: Zero internal Kafka experience; existing Redis proficiency.
- **Timeline**: Maximum 2 weeks for setup/migration.
- **Budget**: Limited; managed Kafka (Confluent) is currently cost-prohibitive.
- **Requirements**: At-least-once delivery for general events; exactly-once for billing; support for future WebSockets; support for exponential backoff retries.

## Decision
We will use **Redis Streams** as the message backbone for the notification subsystem.

### Justification
Given the constraints, Redis Streams provides the optimal balance of technical capability and operational simplicity.

1. **Operational Complexity**: We already operate Redis in production. Adding Streams requires no new infrastructure, no new monitoring stacks, and no new binaries to manage. Kafka would introduce a significant operational burden (Zookeeper/KRaft, JVM tuning) for a team with no Kafka experience.
2. **Throughput & Latency**: Our current peak is 500 req/s. A 10x growth (5,000 req/s) is well within the capabilities of a single Redis instance or a small cluster. Kafka's throughput is overkill for our current and mid-term scale.
3. **Ordering & Consumer Groups**: Redis Streams supports consumer groups (`XGROUP`), allowing us to distribute notification processing across multiple workers while maintaining message ordering per stream.
4. **Message Retention**: Streams allow for capped streams (`MAXLEN`), ensuring we don't exhaust memory while keeping enough history for retries and auditing.
5. **Exactly-Once Semantics**: While neither system provides "magic" exactly-once delivery across the network, Redis Streams combined with our existing PostgreSQL database allows us to implement **idempotent processing**. By recording the processed Message ID in a PostgreSQL table within the same transaction as the business logic update, we achieve effectively exactly-once semantics for billing notifications.

## Consequences

### Pros
- **Zero Infra Overhead**: Leverages existing Redis deployment.
- **Fast Time-to-Value**: Implementation can begin immediately without procurement or complex cluster setup, fitting the 2-week window.
- **Low Latency**: Sub-millisecond persistence and delivery.
- **Simplified Tooling**: Team uses tools they already know for debugging (redis-cli).

### Cons
- **Memory Bound**: Redis stores data in RAM. We must be disciplined with `MAXLEN` and consumer acknowledgment to avoid OOM (Out of Memory) errors.
- **Durability Trade-off**: While AOF provides durability, Redis is generally less durable than Kafka's disk-centric commit log in the event of a catastrophic total cluster failure. However, for notifications, the trade-off is acceptable.

## Alternatives Considered

### Apache Kafka
Rejected for the following reasons:
- **Operational Risk**: The "Kafka tax" (setup, tuning, and maintenance) is too high for a 6-person team without an infra engineer.
- **Over-engineering**: Kafka's strengths (massive scale, long-term retention) are not required for our current or 10x scaling target.
- **Cost**: Managed services are too expensive; self-hosting would violate the 2-week delivery constraint.
- **Complexity**: The learning curve for a team with zero Kafka experience would delay the resolution of the current production timeouts.
