# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and embedded within the HTTP request cycle, leading to request timeouts (spikes up to 8s), silent failures during provider outages, and cascading failures that exhaust connection pools. 

The system must evolve to support:
- Asynchronous processing to decouple notifications from user requests.
- Robust retry mechanisms with exponential backoff.
- Delivery guarantees: at-least-once for general notifications and exactly-once for critical billing events.
- Future support for real-time WebSocket push notifications.
- Ability to handle 10x current peak traffic (~5,000 req/s).

**Constraints:**
- Team: 6 engineers (no dedicated infra expert), no prior Kafka experience.
- Infrastructure: Existing Redis deployment in production.
- Timeline: Value must be delivered within 2 weeks of setup/migration.
- Budget: Modest; managed Kafka services (e.g., Confluent) are currently cost-prohibitive.

## Decision
We will use **Redis Streams** as the primary message backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives for a reliable distributed queue (consumer groups, message acknowledgement, and persistence) while aligning with our current operational capabilities and constraints.

1. **Operational Simplicity**: We already run Redis in production. Adding Streams requires no new infrastructure software, no new monitoring stacks, and no specialized "Kafka-engineer" knowledge, fitting the 2-week delivery window.
2. **Performance**: Redis Streams can easily handle the targeted 5,000 req/s throughput with sub-millisecond latency, far exceeding our current needs.
3. **Consumer Groups**: Support for consumer groups allows us to scale processing horizontally across multiple workers, providing the decoupling needed to prevent cascading failures.
4. **Delivery Guarantees**: Through the use of `XACK` (acknowledgments) and the Pending Entries List (PEL), we can implement at-least-once delivery. For critical billing events, we will implement **idempotent consumers** (checking a `processed_event_id` in PostgreSQL) to achieve effectively exactly-once semantics.
5. **Future Proofing**: Redis's pub/sub and stream capabilities provide a direct path to integrating WebSocket push notifications.

## Consequences
### Pros
- **Rapid Deployment**: Zero new infrastructure overhead; minimal setup time.
- **Low Latency**: Extremely fast ingestion and consumption.
- **Reduced Complexity**: Keeps the stack lean; avoids the "operational tax" of managing a Zookeeper/Kafka cluster.
- **Resource Efficiency**: Leverages existing memory and hardware allocated to Redis.

### Cons
- **Memory Constraints**: Unlike Kafka, which stores data on disk, Redis is primarily in-memory. We must implement strict stream capping (`XADD ... MAXLEN ~`) to prevent memory exhaustion.
- **Limited Retention**: Long-term archival of messages is not native to Redis Streams; we must move old messages to PostgreSQL or S3 if auditing is required beyond a few days.
- **At-Most-Once Risk**: Without a carefully implemented ACK loop and recovery worker for pending messages, we risk losing data on consumer crashes.

## Alternatives Considered
### Apache Kafka
While Kafka is the industry standard for high-throughput event streaming, it was rejected for the following reasons:
- **Operational Complexity**: Kafka requires a significant management overhead (JVM tuning, Zookeeper/KRaft management, partition balancing). With no dedicated infra engineer, the risk of misconfiguration is high.
- **Steep Learning Curve**: The team has zero Kafka experience. The time required to reach operational proficiency would exceed the 2-week delivery constraint.
- **Cost**: Self-hosting Kafka at the required reliability level increases AWS spend, and managed versions like Confluent Cloud are currently outside the modest budget.
- **Overkill**: Kafka's strengths (massive multi-terabyte retention, complex stream processing) are not required for a notification system at our current and targeted scale.
