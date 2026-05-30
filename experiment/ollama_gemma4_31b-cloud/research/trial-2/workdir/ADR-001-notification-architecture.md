# ADR-001: Notification Subsystem Architecture

## Title
Selection of Message Broker for Asynchronous Notification Processing

## Status
Proposed

## Context
The current synchronous notification system is causing request timeouts (averaging 800ms, spiking to 8s), silent failures, and cascading system failures due to connection pool exhaustion. We need to decouple notifications from the HTTP request cycle to support retries with exponential backoff and provide delivery guarantees for billing-critical events.

**Key Constraints:**
- **Team:** 6 engineers (no dedicated infra/DevOps).
- **Existing Stack:** AWS, Python/Flask, PostgreSQL, and Redis.
- **Experience:** No internal Kafka expertise.
- **Timeline:** Maximum 2 weeks for setup/migration to reach initial value.
- **Budget:** Modest; managed Kafka (Confluent) is cost-prohibitive.
- **Scale:** Currently 500 req/s peak; must handle 10x growth (5,000 req/s).
- **Requirements:** At-least-once delivery (standard) and Exactly-once (billing).

## Decision
We will use **Redis Streams** as the primary message broker for the notification subsystem.

**Justification:**
1. **Operational Simplicity & Existing Footprint:** We already run Redis in production for session storage and rate limiting. Leveraging Redis Streams avoids the introduction of a new architectural component, requiring zero new infrastructure setup.
2. **Team Expertise & Velocity:** The team has no Kafka experience. Introducing Kafka would require a steep learning curve and likely exceed the 2-week migration window for setup, tuning, and stabilization.
3. **Sufficient Performance:** Redis Streams can comfortably handle the 10x growth target (5,000 req/s). Given our current peak of 500 req/s, Redis's in-memory nature provides more than enough throughput and lower latency than a distributed log like Kafka for this specific use case.
4. **Delivery Guarantees:** Redis Streams support Consumer Groups (via `XGROUP`), allowing us to implement at-least-once delivery. For the "exactly-once" billing requirement, we will implement an **idempotency layer** at the consumer level using a unique `notification_id` stored in PostgreSQL (the source of truth), as true end-to-end exactly-once semantics in any broker are either computationally expensive or require tight coupling.
5. **Future-Proofing:** Redis's native support for Pub/Sub and Streams aligns perfectly with the requirement to add real-time WebSocket push notifications within the next two quarters.

## Consequences
**Pros:**
- **Zero Infrastructure Overhead:** No new servers or managed services to provision or monitor.
- **Rapid Time-to-Value:** The team can implement the producer/consumer pattern using existing Redis clients immediately.
- **Unified Tooling:** Monitoring and debugging stay within the existing Redis toolset.
- **Low Latency:** Extreme performance for high-frequency notification events.

**Cons:**
- **Memory Constraints:** Unlike Kafka, which persists to disk, Redis Streams consume RAM. We will need to implement a strict `MAXLEN` policy on streams to prevent memory exhaustion.
- **Persistence Trade-off:** While Redis can be configured with AOF/RDB, it is not a "durable log" in the same way Kafka is. In the event of a catastrophic cluster failure, there is a slightly higher risk of data loss compared to Kafka's distributed commit log.
- **Limited Ecosystem:** Kafka has a richer ecosystem of connectors (Kafka Connect) and stream processing (KSQL), which we are forfeiting.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected for the following reasons:
- **Operational Complexity:** Running a production-grade Kafka cluster (including Zookeeper or KRaft) is a significant burden for a 6-person team without a dedicated infra engineer.
- **Budgetary Constraints:** Managed Kafka services are too expensive for our current scale, and self-hosting would consume a disproportionate amount of engineering time.
- **Overkill for Scale:** While Kafka is designed for millions of messages per second, our target 10x growth only reaches ~5,000 req/s. The complexity of Kafka provides no tangible benefit over Redis for this volume.
- **Learning Curve:** The "cost of knowledge" is too high to meet the 2-week delivery constraint.
