# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and coupled to the HTTP request cycle, leading to request timeouts (spiking to 8s), silent failures of emails/webhooks, and cascading failures due to connection pool exhaustion. 

We need to decouple these processes to support asynchronous execution, retries with exponential backoff, and reliable delivery for billing-critical events. The system must be capable of handling 10x current traffic (~5,000 req/s peak) and support a future transition to real-time WebSocket pushes.

**Constraints:**
- Team: 6 engineers (no dedicated DevOps/Infra).
- Experience: Zero Kafka experience; existing Redis production footprint.
- Timeline: Must deliver value within 2 weeks.
- Budget: Limited; managed Kafka services are currently cost-prohibitive.
- Critical Requirement: Exactly-once semantics for billing notifications.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
1. **Operational Simplicity**: We already operate Redis in production. Adding Streams requires no new infrastructure, no new binaries to manage, and no additional monitoring stack, fitting the 2-week delivery window.
2. **Throughput and Performance**: At 5,000 req/s (10x growth), Redis Streams easily handles the load with sub-millisecond latency, far exceeding our current and projected requirements.
3. **Consumer Group Model**: Redis Streams provides consumer groups, allowing us to distribute the notification load across multiple workers and track message acknowledgement (ACK), ensuring at-least-once delivery.
4. **Exactly-Once Semantics**: While neither system provides "true" exactly-once delivery in a distributed environment without coordination, we will implement **idempotent consumers** using Redis as a deduplication store. Given we already have Redis, this is the most efficient way to achieve exactly-once processing for billing events.
5. **Future-Proofing**: Redis's Pub/Sub and Streams are natural complements for the planned WebSocket push notifications, allowing us to route messages to specific user-session workers with minimal architectural change.

## Consequences
**Pros:**
- **Immediate Velocity**: Zero setup time for infrastructure; team uses existing knowledge.
- **Low Overhead**: Minimal memory and CPU footprint compared to a JVM-based Kafka cluster.
- **Unified Stack**: Simplifies the mental model and operational burden for a small 6-person team.
- **Fast Iteration**: Ease of inspection and debugging using existing Redis CLI tools.

**Cons:**
- **Retention Limits**: Redis is in-memory. While we can cap stream length (XADD MAXLEN), we cannot store years of message history on disk as easily as Kafka. However, notifications are transient by nature; historical logs should reside in PostgreSQL.
- **Lack of Native Ecosystem**: We lose the vast Kafka Connect ecosystem for integrating with third-party sinks, but our requirements are simple (email/webhooks), which are easily implemented in Python.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Complexity**: Kafka requires Zookeeper (or KRaft), significant JVM tuning, and dedicated management. With no infrastructure engineer, the "operational tax" would outweigh the technical benefits.
- **Learning Curve**: The team has zero Kafka experience. The time to reach production-grade stability would exceed the 2-week constraint.
- **Over-Engineering**: Kafka is designed for massive throughput (millions of events/sec) and long-term durable storage. Our 10x growth target (~5k req/s) is well within the capabilities of a single Redis instance or a small cluster.
- **Cost**: Self-hosting is a time-sink, and managed services (Confluent) are outside the current budget.
