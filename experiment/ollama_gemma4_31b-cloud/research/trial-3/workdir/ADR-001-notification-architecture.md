# ADR-001-notification-architecture

## Title
Notification Subsystem: Redis Streams vs. Apache Kafka

## Status
Proposed

## Context
The current synchronous notification system in the Flask monolith is causing request timeouts (up to 8s spikes), silent failures during provider outages, and cascading failures due to connection pool exhaustion. 

We must decouple notifications from the HTTP request cycle to support:
- Asynchronous processing with exponential backoff retries.
- At-least-once delivery for billing-critical events and exactly-once where feasible.
- Future support for real-time WebSocket push notifications.
- Ability to scale 10x (up to ~5,000 req/s peak).

**Constraints:**
- Engineering team of 6 (no dedicated infra engineer).
- Existing production Redis instance.
- Zero Kafka experience on the team.
- Setup/migration must take ≤ 2 weeks.
- Modest budget (no high-cost managed Confluent Cloud).

## Decision
We will use **Redis Streams**.

### Justification
Redis Streams is the optimal choice because it provides the necessary streaming primitives (consumer groups, message persistence, and offsets) while aligning with the team's operational capacity and existing infrastructure.

1. **Operational Complexity**: The team already manages Redis. Introducing Kafka would require learning a new ecosystem (Zookeeper/KRaft, JVM tuning, partition management) and adding a significant operational burden to a small team without a dedicated infra engineer.
2. **Deployment Speed**: Since Redis is already in production, enabling Streams is a configuration/code change. We can meet the < 2-week delivery target immediately, whereas Kafka would require provisioning, securing, and tuning a new cluster.
3. **Performance & Scaling**: With a peak of 500 req/s and a 10x target (5,000 req/s), Redis Streams can easily handle the throughput. While Kafka scales higher, it is overkill for this scale.
4. **Delivery Guarantees**:
   - **At-least-once**: Achieved through Redis Consumer Groups and the `XACK` (acknowledge) mechanism.
   - **Exactly-once (Billing)**: We will implement idempotency keys at the consumer level (PostgreSQL `UNIQUE` constraint on `notification_id`) to simulate exactly-once semantics. This is a more pragmatic approach than Kafka's transactional producers given our constraints.
5. **Future Proofing**: Redis Streams supports the fan-out patterns required for the upcoming WebSocket push notifications.

## Consequences
**Pros:**
- **Minimal Overhead**: Leverages existing Redis infrastructure; no new "infrastructure silos."
- **Low Latency**: Extremely low end-to-end latency for message production and consumption.
- **Rapid Iteration**: The team can implement the prototype and migrate without a steep learning curve.
- **Cost Effective**: No additional licensing or heavy infrastructure costs.

**Cons:**
- **Memory Constraints**: Unlike Kafka's disk-based persistence, Redis primarily stores data in RAM. We will need to implement strict `XTRIM` policies to prevent memory exhaustion.
- **Durability Trade-off**: Redis persistence (RDB/AOF) is generally less durable than Kafka's distributed commit log. However, for notification events, the risk is acceptable compared to the operational risk of Kafka.
- **Limited Ecosystem**: Fewer third-party "connectors" compared to the Kafka Connect ecosystem.

## Alternatives Considered
**Apache Kafka**
Rejected for the following reasons:
- **Operational Overkill**: The "tax" of managing Kafka (JVM, ZooKeeper/KRaft, partition balancing) is too high for a 6-person team.
- **Learning Curve**: The team has zero Kafka experience; the time to reach "production-ready" proficiency would exceed the 2-week window.
- **Resource Cost**: Both in terms of human effort and infrastructure spend (RAM/CPU requirements for Kafka brokers).
- **Over-engineering**: Kafka's strengths (massive scale, multi-day retention) are not requirements for this system; 5,000 req/s is well within Redis Streams' capabilities.
