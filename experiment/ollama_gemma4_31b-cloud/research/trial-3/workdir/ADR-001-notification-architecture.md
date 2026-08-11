# ADR-001-notification-architecture

## Title
Notification Subsystem Architecture: Redis Streams vs. Apache Kafka

## Status
Proposed

## Context
The current notification system is implemented synchronously within the HTTP request cycle of the Flask monolith. This has led to request timeouts (latency spikes up to 8s), silent failures due to lack of retry mechanisms, and cascading failures where slow external webhooks exhaust the backend connection pool. 

The system must be decoupled to support asynchronous processing, exponential backoff retries, and at-least-once delivery guarantees. Specifically, billing-critical notifications (e.g., payment failures) require exactly-once semantics where feasible. 

**Constraints:**
- **Team Size:** 6 engineers (no dedicated infra/DevOps).
- **Existing Stack:** Python/Flask, PostgreSQL, Redis (currently used for sessions/rate limiting).
- **Experience:** Zero Kafka experience within the team.
- **Timeline:** Must deliver value within 2 weeks of setup/migration.
- **Budget:** Modest; managed Kafka (Confluent) is currently cost-prohibitive.
- **Growth:** Must handle 10x traffic growth (~5,000 req/s peak) without re-architecting.

## Decision
We will implement the notification subsystem using **Redis Streams**.

**Justification:**
Redis Streams provides the necessary primitive for a decoupled, asynchronous notification pipeline while aligning perfectly with the team's current operational capacity and infrastructure.

1. **Operational Complexity:** The team already manages Redis in production. Adding Streams requires no new infrastructure, no new monitoring tools, and no specialized knowledge of Zookeeper or Kafka's complex partition/offset management.
2. **Time-to-Value:** Given the 2-week constraint, leveraging an existing tool is the only viable path. Kafka would require a significant learning curve and infrastructure setup period.
3. **Throughput & Scaling:** While Kafka is the industry standard for massive scale, Redis Streams can easily handle the 10x growth target (5k req/s). Redis's in-memory nature provides the low latency required for the upcoming WebSocket push notification requirement.
4. **Ordering & Consumer Groups:** Redis Streams supports Consumer Groups, allowing us to distribute notification processing across multiple workers while maintaining message ordering per stream.
5. **Exactly-Once Semantics:** While "true" exactly-once is difficult in distributed systems, we can achieve it for billing notifications by using Redis's atomicity combined with idempotency keys in PostgreSQL (e.g., a `notification_id` unique constraint on a `delivered_notifications` table).

## Consequences
**Pros:**
- **Immediate Deployment:** No new infrastructure to provision; leverages existing Redis instance.
- **Low Overhead:** Extremely low latency for message ingestion and consumption.
- **Simplified Stack:** Maintains a lean infrastructure footprint, reducing the cognitive load on the 6-person team.
- **Future-Proof:** Naturally supports the planned real-time WebSocket push notifications.

**Cons:**
- **Memory Constraints:** Unlike Kafka, which persists to disk by default, Redis is primarily in-memory. We will need to implement strict `MAXLEN` capping on streams to prevent OOM (Out of Memory) errors.
- **Persistence Trade-off:** Redis AOF/RDB provides durability, but it is not as robust as Kafka's distributed commit log for long-term message retention. However, for a notification system where messages are short-lived, this is an acceptable trade-off.
- **Limited Ecosystem:** Fewer off-the-shelf connectors compared to Kafka Connect.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Overkill for Scale:** Our 10x growth target is well within Redis's capabilities. Kafka's complexity is only justified at scales orders of magnitude larger than our current or projected needs.
- **Operational Risk:** Without a dedicated infra engineer or prior Kafka experience, the risk of misconfiguring clusters, managing offsets, or handling "rebalance storms" is too high for a 6-person team.
- **Prohibitive Setup Time:** Setting up a production-ready, highly available Kafka cluster (or migrating to a managed service) would exceed the 2-week window for delivering value.
- **Cost:** The budget does not currently support high-tier managed Kafka services, and self-hosting would divert too many engineering hours from product development.
