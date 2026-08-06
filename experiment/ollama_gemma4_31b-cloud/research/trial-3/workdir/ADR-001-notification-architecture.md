# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing HTTP request timeouts (up to 8s) and cascading failures due to slow external webhook endpoints. There are no delivery guarantees or retry mechanisms, which is critical for billing events ("trial expired", "payment failed"). 

The system must decouple notifications from the request cycle, support exponential backoff retries, and guarantee at-least-once delivery (exactly-once where feasible). It must scale to 10x current traffic (~5k req/s peak) and support future WebSocket integration.

**Constraints:**
- **Team:** 6 engineers (no dedicated infra engineer).
- **Existing Stack:** Redis is already in production for sessions/rate limiting.
- **Experience:** Zero team experience with Apache Kafka.
- **Timeline:** Setup/migration must take $\le 2$ weeks.
- **Budget:** Modest; cannot afford high-scale managed Kafka (e.g., Confluent Cloud).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Redis Streams provides the necessary primitives for an asynchronous, durable messaging system while aligning with our current operational capabilities and constraints.

1. **Operational Simplicity & Existing Infrastructure**: We already run Redis. Adding Streams requires no new infrastructure, no new monitoring stack, and no new deployment patterns. Introducing Kafka would require a significant operational shift (ZooKeeper/KRaft management, JVM tuning, partition planning) that our 6-person team cannot absorb within the 2-week window.
2. **Performance**: At 5k req/s (10x growth), Redis Streams is more than sufficient. It handles tens of thousands of writes per second with sub-millisecond latency, comfortably meeting our scaling target.
3. **Consumer Groups & Ordering**: Redis Streams supports Consumer Groups (`XGROUP`), providing the same "competing consumer" pattern as Kafka. This allows us to scale workers horizontally while maintaining order per stream (critical for task update sequences).
4. **Delivery Guarantees**: 
    - **At-least-once**: Achieved via explicit acknowledgments (`XACK`) and Pending Entries Lists (PEL). If a worker fails, the notification remains in the PEL and can be claimed by another worker using `XCLAIM`.
    - **Exactly-once**: For billing events, we will implement idempotency keys at the consumer level (checking the DB before processing). This shifts the complexity to the application layer, where it is more manageable than Kafka's transactional producers.
5. **Message Retention**: We can use `XADD` with `MAXLEN` (approximate capping) to prevent memory exhaustion, which is sufficient for a notification buffer.

## Consequences
### Pros
- **Low Time-to-Value**: Implementation can start immediately using existing Redis instances.
- **Low Overhead**: No additional JVMs or complex cluster management.
- **Unified Tooling**: Existing Redis monitoring and CLI tools apply to the new subsystem.
- **Fast Path to WebSockets**: Redis Pub/Sub or Streams can easily integrate with a WebSocket gateway.

### Cons
- **Memory Bound**: Unlike Kafka (disk-based), Redis is primarily memory-bound. We must strictly monitor and cap stream lengths to avoid OOM events.
- **Simpler Ecosystem**: We lose the rich ecosystem of Kafka Connect and Kafka Streams for complex event processing (which we do not currently need).

## Alternatives Considered
### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity**: The "infrastructure tax" is too high. Managing a production-grade Kafka cluster requires specialized knowledge our team lacks.
- **Overkill for Scale**: While Kafka scales higher, our 10x target (~5k req/s) is well within the capabilities of a single Redis instance or a small cluster.
- **Deployment Timeline**: Setting up, configuring, and verifying a resilient Kafka cluster would likely exceed the 2-week delivery window.
- **Cost**: Managed Kafka services at scale would exceed our current modest budget.
