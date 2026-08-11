# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, blocking HTTP requests and causing latency spikes (up to 8s) and cascading failures due to connection pool exhaustion. We lack delivery guarantees, leading to silent failures for critical billing notifications.

**Key Constraints:**
- **Traffic:** Current peak ~500 req/s; target 10x growth (5,000 req/s).
- **Team:** 6 engineers (3 senior, 3 mid); no dedicated DevOps/Infra engineer.
- **Infrastructure:** Already running Redis in production; no Kafka experience.
- **Timeline:** Must deliver value within 2 weeks.
- **Budget:** Modest; managed Kafka (Confluent) is currently too expensive.
- **Requirements:** At-least-once delivery for billing; exactly-once where feasible; support for future WebSocket integration.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Operational Simplicity:** We already run Redis. Adding Streams requires zero new infrastructure installation, reducing the "time to value" to days rather than weeks. Given the lack of a dedicated infra engineer, the overhead of managing a Kafka cluster (Zookeeper/KRaft, JVM tuning, partition management) is a significant risk.
2. **Performance vs. Scale:** While Kafka handles higher throughput, Redis Streams comfortably supports our 10x target (5,000 req/s). Redis's in-memory nature provides the low latency required for the upcoming real-time WebSocket push notifications.
3. **Consumer Groups:** Redis Streams provides consumer groups (similar to Kafka), allowing us to scale workers horizontally and track message acknowledgement (ACKs), solving the "silent failure" problem.
4. **Reliability:** By utilizing Consumer Groups and the Pending Entries List (PEL), we can implement the required retry logic with exponential backoff.
5. **Billing Guarantees:** While neither provides "out-of-the-box" global exactly-once semantics without application-level idempotency, Redis Streams combined with our existing PostgreSQL database (using an idempotency key/outbox pattern) satisfies the requirement for billing-critical events.

## Consequences
**Pros:**
- **Rapid Deployment:** Immediate start using existing Redis instance.
- **Low Cognitive Load:** The team does not need to learn a complex new ecosystem (Kafka).
- **Resource Efficiency:** No additional JVM overhead or expensive managed service costs.
- **Unified Stack:** Simplifies monitoring and backup strategies by keeping the cache and message bus in one tool.

**Cons:**
- **Memory Constraints:** Unlike Kafka, which persists to disk by default, Redis is primarily in-memory. We must carefully manage stream capping (`MAXLEN`) to avoid OOM (Out of Memory) errors.
- **Persistence Trade-off:** While Redis has AOF/RDB, it is not as durable as Kafka's commit log. In a catastrophic total cluster failure, there is a slightly higher risk of minimal data loss compared to Kafka.
- **Smaller Ecosystem:** Fewer off-the-shelf connectors compared to the Kafka Connect ecosystem.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Complexity:** The "infrastructure tax" is too high for a 6-person team without a DevOps engineer. Setting up and maintaining a production-ready Kafka cluster would exceed the 2-week delivery window.
- **Over-Engineering:** Our 10x growth target (5k req/s) is well within the capabilities of Redis Streams. Kafka's massive scale is unnecessary for our current and near-future needs.
- **Cost:** Self-hosting is operationally expensive (man-hours), and managed services (Confluent) exceed the current budget.
- **Learning Curve:** The team has zero Kafka experience, introducing significant implementation risk.
