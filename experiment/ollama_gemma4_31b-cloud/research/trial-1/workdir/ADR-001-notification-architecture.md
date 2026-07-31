# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system operates synchronously within the HTTP request cycle, leading to request timeouts (up to 8s), silent failures of third-party integrations, and cascading failures that exhaust connection pools. We need to decouple notifications from the request cycle to support async processing, exponential backoff retries, and real-time WebSocket pushes.

**Constraints:**
- **Scale:** Peak 500 req/s, targeting 10x growth (5,000 req/s).
- **Team:** 6 engineers (no dedicated DevOps/Infra).
- **Existing Stack:** Python/Flask, PostgreSQL, Redis.
- **Experience:** No team experience with Kafka.
- **Timeline:** Delivery of value within 2 weeks.
- **Critical Requirement:** Exactly-once semantics for billing notifications.

## Decision
We will use **Redis Streams** as the messaging backbone for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitive for a distributed append-only log while leveraging our existing infrastructure. Given the team's size and the urgent 2-week window, the operational overhead of Kafka is prohibitive. Redis Streams supports Consumer Groups, which allow us to scale processing horizontally and track message acknowledgment, satisfying the at-least-once delivery requirement for billing events. For exactly-once semantics, we will implement the **Idempotent Consumer pattern** using PostgreSQL (which we already run) to track processed event IDs, as neither Redis nor Kafka provides true end-to-end exactly-once delivery without significant complexity.

## Consequences
### Pros
- **Low Operational Overhead:** No new infrastructure to manage; we already run Redis in production.
- **Fast Time-to-Market:** Minimal setup time allows the team to focus on the retry logic and consumer implementation immediately.
- **Performance:** Extremely high throughput and low latency, easily handling the 10x growth target (5,000 req/s).
- **Unified Stack:** Simplifies the architectural footprint and reduces the cognitive load on a small engineering team.

### Cons
- **Memory Constraints:** Redis is primarily in-memory. We must carefully manage stream retention policies (e.g., `XTRIM` or `MAXLEN`) to prevent OOM errors as traffic grows.
- **Durability Trade-off:** While Redis AOF provides persistence, it is generally less durable than Kafka's disk-based segment logs in the event of a catastrophic cluster failure.

## Alternatives Considered
### Apache Kafka
**Reason for Rejection:**
- **Operational Complexity:** Kafka requires Zookeeper (or KRaft) and significant tuning of JVM, partitions, and replication factors. Without a dedicated infrastructure engineer, the risk of misconfiguration causing production instability is high.
- **Learning Curve:** The team has zero Kafka experience. The time required to reach operational competence would exceed the 2-week window.
- **Cost:** Managed solutions like Confluent Cloud exceed the current modest budget.
- **Overkill:** At 5,000 req/s, Kafka's massive throughput capabilities are not required; Redis Streams is more than sufficient for this load.
