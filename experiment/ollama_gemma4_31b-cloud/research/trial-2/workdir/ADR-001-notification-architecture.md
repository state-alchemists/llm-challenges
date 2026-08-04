# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to request timeouts (up to 8s), silent failures, and cascading failures that exhaust connection pools. We require a decoupled, asynchronous architecture to support:
- **Throughput**: Handling current peak loads (500 req/s) and scaling 10x.
- **Reliability**: Retry with exponential backoff and dead-letter queues (DLQ).
- **Delivery Guarantees**: At-least-once delivery for all notifications and exactly-once semantics for critical billing events.
- **Future Growth**: Support for real-time WebSocket pushes within 6 months.

**Constraints:**
- **Team**: 6 engineers (3 senior, 3 mid) with no dedicated infrastructure/DevOps engineer.
- **Existing Stack**: Already running Redis in production for sessions/rate limiting.
- **Skillset**: Zero team experience with Apache Kafka.
- **Timeline**: Setup and migration must deliver value within 2 weeks.
- **Budget**: Modest; managed Kafka services (e.g., Confluent) are cost-prohibitive.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
The primary drivers for this decision are operational simplicity and the existing team's familiarity with the stack. Redis Streams provides the necessary primitives—consumer groups, message persistence, and offsets—to solve the decoupling and reliability problems without introducing the massive operational overhead of a Kafka cluster.

- **Operational Complexity**: Redis is already in production. Adding Streams requires no new infrastructure, whereas Kafka would require deploying and managing a new cluster (Zookeeper/KRaft), which the team is not equipped to do without a dedicated infra engineer.
- **Throughput & Latency**: Redis Streams easily handles the current peak (500 req/s) and the 10x growth target (5,000 req/s), as it operates primarily in-memory with asynchronous disk persistence.
- **Delivery Guarantees**: 
    - **At-least-once**: Achieved via Consumer Groups and explicit acknowledgments (`XACK`).
    - **Exactly-once (Billing)**: Since Redis does not provide native distributed transactions across the stream and the database, we will implement this via **idempotent consumers**. Each billing notification will carry a unique `event_id`, and consumers will use a "processed_events" table in PostgreSQL to ensure an event is not processed twice.
- **Time to Value**: Implementation can begin immediately using the existing Redis instance. Setup and initial migration can be completed within days, well under the 2-week constraint.

## Consequences
**Pros:**
- **Near-zero setup time**: Leverages existing infrastructure and expertise.
- **Low overhead**: Minimal resource footprint compared to Kafka.
- **Fast iteration**: Simple API for producing and consuming messages.
- **Unified stack**: Reduces the number of distinct technologies the team must maintain.

**Cons:**
- **Memory Constraints**: Redis stores streams in RAM. We must implement a strict `MAXLEN` policy to prune old messages and prevent OOM crashes.
- **Durability Trade-off**: While Redis provides AOF/RDB persistence, it is not as durable as Kafka's disk-first commit log. However, for notifications (where we can retry from the source if a rare crash occurs), this is an acceptable trade-off.
- **Scaling Ceiling**: While 5,000 req/s is well within Redis's limits, extreme scale (millions of events/sec) would eventually require a migration to Kafka.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected primarily due to the **operational gap**. 
- **Complexity**: Kafka's deployment and tuning (JVM, partitions, replication factors, Zookeeper/KRaft) are complex. Without an infra engineer, the risk of misconfiguration leading to production instability is high.
- **Cost**: The team cannot afford managed Kafka services, and the manual overhead of self-hosting outweighs the technical benefits for our current scale.
- **Over-engineering**: Kafka provides superior durability and massive throughput that exceeds our 10x growth target. Using it now would violate the "minimal surface area" principle and exceed the 2-week delivery window.
- **Learning Curve**: The team has zero Kafka experience, meaning the "setup" phase would be a research project rather than a delivery project.
