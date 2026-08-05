# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing HTTP request timeouts (up to 8s), silent failures due to lack of retries, and cascading failures that exhaust connection pools. We need to decouple notifications from the request cycle to support asynchronous processing, exponential backoff retries, and strict delivery guarantees for billing-critical events ("trial expired", "payment failed").

**Constraints:**
- **Team:** 6 engineers (no dedicated infra/DevOps).
- **Current Stack:** Python/Flask, PostgreSQL, Redis (already in production for sessions/rate limiting).
- **Experience:** Zero Kafka experience on the team.
- **Timeline:** Must deliver value within 2 weeks.
- **Growth:** Must scale 10x from current peak (~500 req/s to 5,000 req/s).
- **Requirements:** Exactly-once semantics for billing notifications; support for future WebSocket integration.

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
1. **Operational Simplicity:** We already operate Redis in production. Adding Streams requires no new infrastructure, binaries, or JVM tuning, which is critical for a 6-person team without a dedicated infra engineer.
2. **Implementation Speed:** Given the "2-week window" constraint, leveraging an existing dependency allows for immediate development. Kafka would require cluster setup, Zookeeper/KRaft configuration, and a steep learning curve.
3. **Performance:** Redis Streams easily handle the 10x growth target (5,000 req/s). Memory-resident throughput is significantly higher than the current requirements.
4. **Consumer Groups:** Redis Streams provide consumer groups (similar to Kafka), enabling the requested decoupling and parallel processing of notifications.
5. **Billing Guarantees:** While Redis is primarily in-memory, we will ensure the "Exactly-Once" requirement for billing by combining Redis Streams' acknowledgement (ACK) mechanism with idempotent processing in the Python workers (using a PostgreSQL `processed_notifications` table to track unique event IDs).

## Consequences
**Pros:**
- **Zero Infrastructure Overhead:** No new tools to monitor or maintain.
- **Low Latency:** Extremely fast produce/consume cycles.
- **Low Risk:** The team is already familiar with Redis; onboarding is near-zero.
- **Path to WebSockets:** Redis Pub/Sub or Streams integrate natively with WebSocket architectures for the planned Q2 push.

**Cons:**
- **Memory Constraints:** Unlike Kafka's disk-based persistence, Redis Streams consume RAM. We must implement a strict `MAXLEN` policy to prevent OOM (Out of Memory) errors during spikes.
- **Persistence Trade-off:** Redis AOF/RDB provides durability, but not with the same rigorous disk-sync guarantees as Kafka's distributed commit log. This is mitigated by our idempotency layer in PostgreSQL for billing events.

## Alternatives Considered
**Apache Kafka**
Rejected for the following reasons:
- **Operational Complexity:** Managing a Kafka cluster (even a small one) is a significant burden for a team of 6 without infra expertise.
- **Cost:** Managed options like Confluent Cloud exceed the current "modest" budget.
- **Time-to-Value:** The learning curve and setup time would exceed the 2-week delivery window.
- **Overkill:** At 5,000 req/s, the massive throughput and partition scaling of Kafka are not yet required. Redis Streams provides a sufficient middle ground between a simple task queue and a full-scale event streaming platform.
