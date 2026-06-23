# ADR 001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current synchronous notification system is causing request timeouts (spiking to 8s), silent failures during provider outages, and cascading failures due to connection pool exhaustion. We must decouple notifications from the HTTP request cycle to ensure system stability and reliability.

**Key Requirements & Constraints:**
- **Scale:** Current peak 500 req/s; must handle 10x growth (5,000 req/s).
- **Guarantees:** At-least-once delivery for general notifications; exactly-once semantics for billing-critical events.
- **Operations:** 6-person engineering team with no dedicated infra engineer. No existing Kafka experience.
- **Infrastructure:** Redis is already running in production for sessions and rate limiting.
- **Timeline:** Setup and migration must be completed within 2 weeks to deliver value.
- **Future-proofing:** Must support real-time WebSocket push notifications within 2 quarters.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
1. **Operational Simplicity:** Since we already operate Redis, there is zero new infrastructure overhead. Introducing Kafka would require deploying and managing a new cluster (Zookeeper/KRaft, brokers), which is unrealistic for a 6-person team without a dedicated infra engineer.
2. **Time-to-Value:** Redis Streams can be implemented using existing client libraries in our Flask monolith. We can meet the 2-week migration window, whereas a Kafka rollout would likely exceed this due to configuration and learning curves.
3. **Performance:** At 5,000 req/s (10x target), Redis Streams easily handles the throughput. Its in-memory nature ensures the low latency required to remove the current 800ms-8s blocking overhead.
4. **Consumer Groups:** Redis Streams supports Consumer Groups, allowing us to scale worker processes horizontally and maintain offset tracking, providing the "at-least-once" delivery guarantee.
5. **Exactly-Once Semantics:** While neither system provides "magic" exactly-once delivery across the entire network hop to a 3rd party API, Redis allows us to implement an idempotent consumer pattern efficiently by using the same Redis instance to store processed message IDs (idempotency keys) atomically.

## Consequences
**Pros:**
- **Low Overhead:** No new binaries to install or clusters to manage.
- **Rapid Deployment:** Immediate transition from synchronous to asynchronous processing.
- **Unified Stack:** Leverage existing Redis expertise and monitoring.
- **WebSocket Ready:** Redis Pub/Sub or Streams can easily feed into a WebSocket layer for the upcoming real-time requirement.

**Cons:**
- **Memory Bound:** Unlike Kafka, which persists to disk by default, Redis is primarily in-memory. We must configure appropriate eviction policies (e.g., `noeviction`) and stream capping (`XADD MAXLEN`) to prevent OOM if consumers lag significantly.
- **Persistence Risk:** While AOF/RDB provide persistence, Kafka offers stronger durability guarantees for massive backlogs. However, for notification logs, the trade-off is acceptable given the team's size.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected due to the following:
- **Operational Complexity:** The "Kafka tax" (management of brokers and metadata) is too high for a small team.
- **Learning Curve:** The team has zero Kafka experience; the time required to reach operational competence would violate the 2-week delivery constraint.
- **Over-Engineering:** Kafka's massive throughput and long-term retention capabilities are overkill for 5,000 req/s of notification events.
- **Cost:** Managed Kafka (Confluent) is explicitly outside the current modest budget.
