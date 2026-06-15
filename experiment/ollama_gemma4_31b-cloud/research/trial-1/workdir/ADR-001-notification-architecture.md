# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and embedded within the HTTP request cycle, leading to high latency (spikes to 8s), silent failures, and cascading system failures due to slow external webhooks. 

The system must evolve to:
- Decouple notifications from the request cycle.
- Provide at-least-once delivery for general events and exactly-once semantics for billing-critical events.
- Support exponential backoff retries.
- Scale to 10x current traffic (peak ~5,000 req/s).
- Enable future WebSocket integration.

**Constraints:**
- Engineering team of 6 (no dedicated infra engineer).
- Zero internal experience with Apache Kafka.
- Existing production deployment of Redis.
- Implementation window of < 2 weeks for initial value.
- Limited budget (cannot afford full-scale managed Kafka/Confluent).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Operational Simplicity:** Since Redis is already running in production for sessions and rate limiting, the operational overhead is near zero. Adding Streams does not require new infrastructure, new monitoring stacks, or new failure modes for the team to manage.
2. **Development Velocity:** The 2-week constraint is critical. Redis Streams provides consumer groups and message persistence with a much lower learning curve than Kafka, allowing the team to deliver async processing and retries immediately.
3. **Performance:** With a peak target of 5,000 req/s, Redis Streams easily handles the throughput requirements without the complexity of partition management and Zookeeper/KRaft overhead.
4. **Exactness & Guarantees:** By leveraging Redis Streams' acknowledgement (`XACK`) and pending entries list (`XPENDING`), we can implement at-least-once delivery. For billing-critical "exactly-once" requirements, we will implement **idempotent consumers** (using a unique event ID in PostgreSQL), which is the industry-standard way to achieve exactly-once semantics regardless of the broker.
5. **Future Proofing:** Redis Pub/Sub or Streams can be easily integrated with a WebSocket layer (e.g., using a Python asyncio worker) to meet the 2-quarter goal for real-time push notifications.

## Consequences
**Pros:**
- **Rapid Deployment:** No new binaries to install or clusters to tune.
- **Low Cognitive Load:** The team utilizes an existing toolset, reducing the risk of misconfiguration.
- **Resource Efficiency:** Avoids the high memory and CPU overhead associated with a minimal Kafka cluster.
- **Sufficient Scale:** Easily meets the 10x growth target given the current and projected traffic.

**Cons:**
- **Retention Limits:** Unlike Kafka's long-term disk-based retention, Redis is primarily memory-bound. We must implement strict `MAXLEN` capping on streams to prevent OOM (Out of Memory) events.
- **Limited Ecosystem:** Fewer "out-of-the-box" connectors (e.g., Kafka Connect) compared to the Kafka ecosystem, meaning more custom glue code for new integrations.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **High Operational Complexity:** Managing a Kafka cluster (even with KRaft) requires significant expertise in JVM tuning, disk I/O, and partition balancing—skills not currently present in the 6-person team.
- **Prohibitive Setup Time:** Setting up a production-grade, resilient Kafka cluster and integrating it into the Flask monolith would likely exceed the 2-week window for initial value delivery.
- **Over-Engineering:** Kafka is designed for massive throughput (millions of events/sec) and long-term event sourcing. Our peak of 5,000 req/s does not justify the "complexity tax" of Kafka.
- **Cost:** Self-hosting requires dedicated nodes; managed options (Confluent) exceed the current budget.
