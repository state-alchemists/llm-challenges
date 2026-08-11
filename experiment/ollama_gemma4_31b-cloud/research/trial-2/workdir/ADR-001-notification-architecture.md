# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing HTTP request timeouts (spikes up to 8s) and cascading failures due to slow external webhook endpoints. We lack delivery guarantees for billing-critical notifications and have no mechanism for retries or dead-letter queues.

**Constraints & Requirements:**
- **Traffic:** ~500 req/s peak, target 10x growth (5,000 req/s).
- **Team:** 6 engineers (no dedicated Infra/DevOps), no Kafka experience.
- **Infrastructure:** Existing Redis production instance; hosted on AWS.
- **Timeline:** Value must be delivered within 2 weeks of setup.
- **Budget:** Modest; managed Kafka (Confluent) is currently cost-prohibitive.
- **Guarantees:** At-least-once for most; exactly-once for billing events.
- **Future:** WebSocket integration planned within 2 quarters.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitives (consumer groups, message persistence, and acknowledgement) to decouple our notifications while fitting within our operational constraints.

1. **Operational Simplicity:** We already run Redis in production. Adding Streams requires no new infrastructure, avoiding the steep learning curve and operational overhead of Kafka (Zookeeper/KRaft, JVM tuning, partition management). Given our 6-person team without an Infra engineer, this is the primary driver.
2. **Performance:** Redis Streams can easily handle the 10x growth target (5,000 req/s). Being in-memory, it offers lower latency than Kafka for the current scale of our notifications.
3. **Consumer Groups:** Redis Streams supports consumer groups, allowing us to scale worker processes horizontally to handle email and webhook delivery.
4. **Delivery Guarantees:**
   - **At-least-once:** Achieved via the Pending Entries List (PEL) and `XACK`. If a worker crashes, the message remains in the PEL and can be claimed by another worker using `XCLAIM`.
   - **Exactly-once (Billing):** While neither Kafka nor Redis provides "out-of-the-box" exactly-once across the entire distributed system (including side effects like sending an email), we will implement **idempotency keys** at the consumer level. The consumer will check a Redis set/key before processing a billing event to ensure it is only executed once.
5. **Timeline:** Implementation can begin immediately using the existing Redis instance, meeting the <2 week delivery constraint.

## Consequences
**Pros:**
- **Zero Infra Overhead:** No new clusters to provision, monitor, or patch.
- **Low Latency:** Sub-millisecond ingestion of notification events.
- **Fast Time-to-Market:** The team can leverage existing Python/Redis libraries immediately.
- **Resource Efficiency:** Avoids the heavy memory/CPU footprint of a Kafka cluster for our current scale.

**Cons:**
- **Memory Bound:** Unlike Kafka, which persists to disk by default, Redis is primarily in-memory. We must carefully manage `MAXLEN` on streams to prevent OOM (Out of Memory) errors.
- **Lower Durability:** While Redis offers AOF/RDB persistence, it is generally less durable than Kafka's distributed commit log in the event of a catastrophic total-cluster failure.
- **Limited Ecosystem:** Fewer off-the-shelf connectors (e.g., Kafka Connect) compared to the Kafka ecosystem.

## Alternatives Considered
**Apache Kafka**
We rejected Kafka for the following reasons:
- **Complexity:** The operational burden of managing Kafka (even a small cluster) is too high for a 6-person team without a dedicated SRE.
- **Learning Curve:** Zero team experience with Kafka would likely push the "time to value" beyond the 2-week constraint.
- **Cost:** Self-hosting requires significant resources; managed services like Confluent are too expensive for the current budget.
- **Overkill:** At 500-5,000 req/s, Kafka's massive throughput capabilities are not required; the added complexity outweighs the marginal gains in durability and scalability.
