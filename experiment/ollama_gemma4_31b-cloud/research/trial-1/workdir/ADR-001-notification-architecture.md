# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to HTTP request timeouts (spikes up to 8s), cascading failures due to slow third-party webhooks, and a lack of delivery guarantees for critical billing events. 

We need to transition to an asynchronous architecture that supports:
- **Decoupling**: Remove notification logic from the request cycle.
- **Reliability**: Support retries with exponential backoff and dead-letter handling.
- **Delivery Guarantees**: At-least-once delivery for general notifications and exactly-once semantics for billing-critical events.
- **Scalability**: Ability to handle 10x current peak traffic (~5,000 req/s) and support future WebSocket integration.

**Constraints:**
- Team size: 6 engineers; no dedicated DevOps/Infra specialist.
- Zero existing Kafka experience.
- Existing Redis infrastructure is already in production.
- Tight timeline: < 2 weeks for initial value delivery.
- Modest budget: Managed high-cost Kafka services are not viable.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Given the team's constraints and the current infrastructure, Redis Streams provides the optimal balance between required technical capabilities and operational overhead.

1. **Operational Simplicity**: We already run Redis. Adding Streams requires no new infrastructure, no new binaries to manage, and no new monitoring stacks. Kafka would introduce a massive operational burden for a 6-person team without a dedicated infra engineer.
2. **Throughput & Latency**: At 500 req/s (and even 5,000 req/s at 10x growth), Redis Streams easily handles the load with sub-millisecond latency. Kafka's throughput is higher, but it is overkill for this scale.
3. **Consumer Groups**: Redis Streams supports consumer groups, allowing us to scale the number of notification workers horizontally and track which messages have been processed, enabling at-least-once delivery.
4. **Ordering Guarantees**: Both systems provide total ordering within a stream/partition. Redis provides sufficient ordering guarantees for our task-based notifications.
5. **Exactly-Once Semantics (EOS)**: While neither system provides "magic" EOS for external side effects (like sending an email), we can achieve EOS for billing notifications by combining Redis Streams with **idempotency keys** stored in our existing PostgreSQL database. The worker will check the DB for the idempotency key before triggering the billing event.
6. **Time to Value**: Implementing Redis Streams takes days; setting up, configuring, and tuning a production-grade Kafka cluster (especially without managed services) would take weeks and likely exceed our 2-week window.

## Consequences
### Pros
- **Zero New Infrastructure**: leverages existing Redis deployment.
- **Low Cognitive Load**: The team can learn Redis Streams rapidly compared to the complexity of Kafka (Zookeeper/KRaft, partitions, offsets, replication factors).
- **Fast Deployment**: Immediate transition to async processing, resolving request timeouts and cascading failures quickly.
- **Efficient Resource Use**: Lower memory and CPU overhead compared to a full Kafka cluster for our specific traffic volume.

### Cons
- **Retention Limits**: Redis is an in-memory store. While we can cap stream length (XADD MAXLEN), we cannot store years of history like Kafka's disk-based segments. However, notifications are transient by nature, so this is acceptable.
- **Smaller Ecosystem**: Fewer "off-the-shelf" connectors (Kafka Connect) compared to Kafka. We will need to write simple Python consumers, which is trivial for our team.

## Alternatives Considered
### Apache Kafka
Kafka was rejected for the following reasons:
- **Operational Complexity**: The "Kafka Tax" is too high for a 6-person team. Managing brokers, partitions, and consumer offsets without a dedicated infra engineer introduces significant risk.
- **Over-engineering**: Our scale (peak 500-5,000 req/s) does not justify the complexity of a distributed log system.
- **Cost**: Without a budget for Confluent Cloud, self-hosting Kafka would consume too much engineering time and infrastructure spend.
- **Learning Curve**: No existing Kafka experience on the team would guarantee a slow rollout and a higher probability of misconfiguration leading to data loss.
