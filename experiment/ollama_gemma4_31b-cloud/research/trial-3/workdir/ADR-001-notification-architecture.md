# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and coupled to the HTTP request cycle, leading to average latencies of 800ms and spikes up to 8s. Critical failures include:
- **Request Timeouts**: Slow external providers (email/webhooks) block API responses.
- **Reliability**: No retry mechanism or dead-letter queues (DLQ); notifications are silently dropped on failure.
- **Stability**: Slow webhooks cause connection pool exhaustion, triggering cascading failures across the monolith.
- **Guarantees**: Lack of delivery guarantees for billing-critical events (e.g., payment failures).

**Constraints:**
- **Team**: 6 engineers (3 senior, 3 mid) with no dedicated infrastructure engineer and zero Kafka experience.
- **Infrastructure**: Existing Redis instance in production; hosted on AWS.
- **Budget**: Limited; managed Kafka (Confluent) is cost-prohibitive.
- **Timeline**: Maximum 2 weeks for setup/migration.
- **Scaling Target**: Must handle 10x current peak (~5,000 req/s) and support future WebSocket integration.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitives (consumer groups, offsets, and persistence) to decouple notifications from the request cycle while minimizing operational overhead. Given the team size and the existing production Redis footprint, the "cost of adoption" is near zero compared to the steep learning curve and operational burden of Kafka.

- **Throughput**: Redis Streams easily handles the target 5,000 req/s on a single primary instance, which is well within the capabilities of the existing AWS Redis setup.
- **Ordering & Consumer Groups**: Redis Streams supports consumer groups, allowing us to distribute notifications across multiple workers while maintaining ordering per stream.
- **Operational Complexity**: Since Redis is already in production, there is no new infrastructure to provision, monitor, or secure.
- **Implementation Speed**: The team can implement a producer-consumer pattern with Redis Streams in days, meeting the <2-week constraint.
- **Billing Guarantees**: By using `XACK` (acknowledgments) and tracking pending entries (PEL), we can implement at-least-once delivery. To achieve exactly-once for billing, we will implement idempotency keys at the consumer level (database-backed), which is a requirement regardless of the broker choice.

## Consequences
**Pros:**
- **Low Overhead**: No new infrastructure; leverages existing Redis expertise.
- **Latency**: Extremely low producer latency, immediately removing notifications from the HTTP request cycle.
- **Rapid Iteration**: Faster time-to-market for retries and DLQ patterns using Redis lists for failed events.
- **Future-Proof**: Redis Pub/Sub or Streams can easily feed into the planned WebSocket push notifications.

**Cons:**
- **Memory Constraints**: Unlike Kafka's disk-based storage, Redis stores streams in RAM. We must implement a strict `MAXLEN` capping strategy to prevent OOM (Out of Memory) failures.
- **Durability**: While AOF (Append Only File) provides durability, Redis is generally less durable than Kafka's distributed commit log. However, for notification events, the trade-off is acceptable given the scale.
- **Limited Ecosystem**: Fewer off-the-shelf connectors (e.g., Kafka Connect) compared to the Kafka ecosystem.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Burden**: Managing a Kafka cluster (or even a small one) requires dedicated expertise in Zookeeper/KRaft, partition balancing, and JVM tuning. The team has no Kafka experience and no infra engineer to support it.
- **Setup Time**: Provisioning, configuring, and testing a production-grade Kafka cluster would likely exceed the 2-week migration window.
- **Cost**: Managed services like Confluent Cloud are beyond the current modest budget.
- **Overkill**: Kafka's strengths (massive throughput of GBs/sec, long-term log retention) are not required for the target 5,000 req/s.
