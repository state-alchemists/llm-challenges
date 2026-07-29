# ADR 001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous and embedded within the HTTP request cycle, leading to request timeouts (spikes up to 8s), cascading failures due to slow external webhooks, and a lack of delivery guarantees for billing-critical notifications. 

We need to decouple notifications from the main request flow to improve reliability and latency. The solution must support:
- Asynchronous processing with retries and exponential backoff.
- At-least-once delivery (and exactly-once where feasible) for billing events.
- Ability to handle 10x growth (up to 5,000 req/s peak).
- Future support for WebSocket push notifications.

**Constraints:**
- Team size: 6 engineers; no dedicated DevOps/Infrastructure role.
- Current stack: Python/Flask, PostgreSQL, and an existing Redis instance.
- Timeline: Maximum 2 weeks for initial setup/migration.
- Budget: Modest; avoiding high-cost managed services like Confluent Cloud.
- Expertise: Zero internal Kafka experience.

## Decision
We will use **Redis Streams** as the message backbone for the notification subsystem.

**Justification:**
1. **Operational Simplicity:** We already run Redis in production. Adding Streams requires no new infrastructure, no new monitoring stack, and no additional operational overhead for a team without a dedicated infra engineer.
2. **Time to Value:** Given the 2-week constraint, deploying Redis Streams is nearly instantaneous, whereas Kafka would require significant setup, tuning, and learning curves.
3. **Performance:** Redis Streams easily handles the target 5,000 req/s peak. With our current volume, the overhead of Kafka's JVM and coordination (Zookeeper/KRaft) is unjustified.
4. **Consumer Groups:** Redis Streams provides consumer groups, allowing us to distribute notification processing across multiple worker instances and maintain offsets, ensuring at-least-once delivery.
5. **Exactly-Once Semantics:** While neither provides "true" exactly-once delivery across the entire distributed boundary without external coordination, we will achieve this for billing events by implementing **idempotent consumers** using the existing PostgreSQL database (tracking processed notification IDs), which is the industry-standard approach for both Redis and Kafka.

## Consequences
**Pros:**
- **Low Friction:** Minimal architectural change; leverages existing infrastructure.
- **Low Latency:** Extremely high throughput and low latency for producing and consuming messages.
- **Resource Efficient:** Significantly lower memory and CPU footprint than a Kafka cluster.
- **Developer Velocity:** The team can implement the pattern immediately without learning a complex new ecosystem.

**Cons:**
- **Memory Limits:** Unlike Kafka's disk-based persistence, Redis is primarily in-memory. We must carefully manage stream capping (`XADD MAXLEN`) to prevent OOM (Out of Memory) errors during massive spikes.
- **Persistence Trade-off:** While Redis offers AOF/RDB, it is not as durable as Kafka's distributed commit log. However, for a notification system, the risk of losing a few milliseconds of data in a catastrophic crash is acceptable compared to the operational risk of misconfiguring Kafka.

## Alternatives Considered
**Apache Kafka**
- **Why Rejected:** Kafka is an industry leader for massive scale and high durability, but it is an over-engineered solution for our current needs. The "operational tax" (cluster management, JVM tuning, partition management) is too high for a 6-person team with no Kafka experience. The setup time would exceed the 2-week window, and the cost of a managed service (Confluent) exceeds the current budget. Kafka's strengths in multi-terabyte retention and complex stream processing are not required for a notification dispatcher.
