# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is implemented synchronously within the Flask request cycle, leading to high latency (800ms - 8s spikes), silent failures due to a lack of retry mechanisms, and cascading failures (connection pool exhaustion) when external webhooks are slow. 

**Key Requirements:**
- Decouple notifications from the HTTP cycle to eliminate request timeouts.
- Implement at-least-once delivery for all events and exactly-once semantics for billing-critical notifications.
- Support exponential backoff retries and Dead Letter Queues (DLQ).
- Ability to scale 10x (to ~5,000 req/s peak).
- Support future real-time WebSocket push notifications.

**Constraints:**
- Team size: 6 engineers (none specialized in infrastructure).
- Existing Stack: Python/Flask, PostgreSQL, Redis.
- Experience: Zero Kafka experience on the team.
- Budget: Modest; managed Kafka services (e.g., Confluent) are currently cost-prohibitive.
- Timeline: Value must be delivered within 2 weeks.

## Decision
We will use **Redis Streams** as the message backbone for the notification subsystem.

### Justification
Redis Streams provides a lightweight, persistent append-only log that meets our technical requirements while aligning perfectly with our operational constraints.

1. **Operational Simplicity**: We already run Redis in production. Adding Streams requires no new infrastructure, no new binary installations, and no additional monitoring overhead. Kafka would require a dedicated cluster and a steep learning curve for 6 generalist engineers.
2. **Performance & Scaling**: With a current peak of 500 req/s and a 10x growth target (5k req/s), Redis Streams can easily handle the throughput on a single instance, whereas Kafka's overhead is overkill for this volume.
3. **Delivery Guarantees**:
   - **At-least-once**: Achieved via Consumer Groups and explicit Acknowledgments (`XACK`).
   - **Exactly-once**: Since Redis does not provide native global exactly-once semantics across producer/consumer, we will implement **idempotent consumers**. We will store a `notification_id` in PostgreSQL for billing events; the consumer will check this ID before processing to ensure exactly-once side effects.
4. **Consumer Groups**: Redis Streams' consumer group logic allows us to distribute the load across multiple worker processes, facilitating horizontal scaling of the notification workers.
5. **Rapid Deployment**: Implementation can be done using the existing `redis-py` library, meeting the <2-week time-to-value constraint.

## Consequences
**Pros:**
- **Zero Infrastructure Overhead**: No new servers or complex JVM tuning.
- **Low Latency**: Extremely high throughput and low latency for both producers and consumers.
- **Unified Stack**: Simplifies the mental model for the team (Redis for cache, sessions, and messaging).
- **Future-Proof**: Perfectly suited for the planned WebSocket integration, as Redis is the industry standard for Pub/Sub and real-time push triggers.

**Cons:**
- **Memory Constraints**: Unlike Kafka, which stores data on disk, Redis is primarily in-memory. We must implement a strict `MAXLEN` policy on streams to prevent OOM (Out of Memory) crashes.
- **Limited Ecosystem**: Lacks the massive connector ecosystem (Kafka Connect) available to Kafka. However, our needs are limited to emails and webhooks, which are easily handled in Python.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Complexity**: Managing a Kafka cluster (Zookeeper/KRaft, JVM tuning, partition balancing) is a full-time role. Our team of 6 has no dedicated infra engineer.
- **Over-Engineering**: Kafka is designed for multi-terabyte streams and massive fan-out. Our peak of 5k req/s does not justify the operational "tax" of Kafka.
- **Learning Curve**: The team has zero experience with Kafka. The time required to properly configure and secure a cluster would exceed the 2-week delivery window.
- **Cost**: Self-hosting Kafka increases AWS compute costs, and managed services are currently outside our budget.
