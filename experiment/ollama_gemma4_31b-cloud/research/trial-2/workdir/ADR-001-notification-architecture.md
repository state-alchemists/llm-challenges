# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to request timeouts, silent failures, and cascading failures. We need to decouple notifications from the HTTP request cycle to improve reliability and scalability.

**Key Requirements:**
- Asynchronous processing with retry and exponential backoff.
- At-least-once delivery for general notifications; exactly-once semantics for billing-critical events.
- Support for future real-time WebSocket push notifications.
- Ability to handle 10x growth (up to 5,000 req/s peak).
- Implementation time < 2 weeks.

**Constraints:**
- Engineering team: 6 people (no dedicated infra engineer).
- Current Infrastructure: AWS, Python/Flask, PostgreSQL, Redis (already in production).
- Skillset: No Kafka experience on the team.
- Budget: Modest; avoid high-cost managed services.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitives for a durable, asynchronous message bus (consumer groups, message acknowledgment, and persistence) without the extreme operational overhead of Apache Kafka. Given our team size and the lack of Kafka expertise, the operational risk of managing a Kafka cluster (or the cost of Confluent Cloud) outweighs the theoretical throughput advantages. Since we already operate Redis in production, the incremental complexity is minimal.

To achieve **exactly-once semantics** for billing notifications, we will implement an idempotent consumer pattern using Redis (or PostgreSQL) to track processed message IDs, as neither Kafka nor Redis Streams provides true end-to-end exactly-once delivery without application-level deduplication.

## Consequences
**Pros:**
- **Zero New Infrastructure:** Leverages existing Redis deployment, reducing operational surface area.
- **Low Latency:** Extremely high throughput and low latency for the 5,000 req/s target.
- **Fast Time-to-Value:** The team can implement this within the 2-week window due to existing Redis familiarity.
- **Consumer Groups:** Supports scalable processing across multiple workers with offset tracking.
- **Future-Proof:** Well-suited for the planned WebSocket push notifications via Redis Pub/Sub or Streams.

**Cons:**
- **Memory Constraints:** Redis is an in-memory store; we must carefully manage stream trimming (`XTRIM`) to avoid OOM if consumers lag significantly.
- **Durability Trade-off:** While Redis AOF provides durability, it is generally less robust than Kafka's disk-based commit log for multi-terabyte retention.

## Alternatives Considered

### Apache Kafka
**Rejected.**
- **Operational Complexity:** Kafka requires significant expertise to tune and maintain (JVM, Zookeeper/KRaft, partition management). With no dedicated infra engineer and no team experience, this is a high-risk choice.
- **Overkill for Scale:** Kafka is designed for millions of events per second. Our 10x target (5,000 req/s) is well within the capabilities of a tuned Redis Streams setup.
- **Migration Time:** The setup, configuration, and learning curve would likely exceed the 2-week deadline for delivering initial value.
- **Cost:** Managed Kafka services (like Confluent) would exceed the modest budget constraints at the required scale.
