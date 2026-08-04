# ADR 001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing request timeouts (up to 8s), silent failures of webhooks/emails, and cascading failures due to connection pool exhaustion. Billing-critical notifications lack delivery guarantees.

**Constraints:**
- **Team**: 6 engineers (3 senior, 3 mid), no dedicated infra engineer.
- **Current Stack**: Python/Flask, PostgreSQL, Redis (already in production).
- **Requirements**:
    - Decouple notifications from HTTP cycle (async).
    - Retry with exponential backoff.
    - At-least-once delivery for billing; exactly-once where feasible.
    - Support 10x traffic growth (up to 5,000 req/s peak).
    - Low operational overhead (max 2 weeks setup).
    - Modest budget (cannot afford high-end managed Kafka).

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitive for a durable, append-only log with consumer group support, fitting our requirements without the prohibitive operational cost of Kafka.

1. **Operational Simplicity**: We already run Redis in production. Adding Streams requires no new infrastructure, no new JVM tuning, and no new monitoring stack. The team has zero Kafka experience; introducing it would exceed the 2-week setup constraint and create a significant "bus factor" risk.
2. **Throughput & Performance**: At 5,000 req/s peak, Redis Streams easily handles the load with sub-millisecond latency. Kafka's throughput is overkill for this scale.
3. **Consumer Groups & Reliability**: Redis Streams supports consumer groups, allowing us to distribute notification processing across multiple workers, track acknowledgments (ACKs), and recover pending messages from failed workers.
4. **Ordering**: Redis Streams guarantees ordering per stream, which is sufficient for task-related notifications.
5. **Exactly-Once Semantics**: While neither provides a "magic" exactly-once guarantee across the entire distributed system, Redis combined with PostgreSQL (using an idempotency key/outbox pattern for billing events) allows us to achieve effectively exactly-once processing with much less complexity than Kafka's transaction API.

## Consequences
**Pros:**
- **Immediate Velocity**: Deployment is nearly instantaneous since Redis is already live.
- **Low Overhead**: No new clusters to manage, patch, or scale independently.
- **Unified Stack**: Simplifies the mental model for the team (everything is in Redis/Postgres).
- **Resource Efficiency**: Lower memory and CPU footprint compared to a Kafka cluster.

**Cons:**
- **Memory Bound**: Redis stores data in RAM. We must implement strict retention policies (`XTRIM`) to prevent memory exhaustion as volume grows.
- **Durability Trade-off**: While AOF provides durability, it is generally less robust than Kafka's disk-first architecture. However, for notifications, this risk is acceptable if combined with a database-backed outbox for billing.
- **Limited Ecosystem**: Fewer off-the-shelf "connectors" compared to the Kafka Connect ecosystem.

## Alternatives Considered
**Apache Kafka**
- **Why rejected**: 
    - **Operational Complexity**: Requires Zookeeper (or KRaft), JVM tuning, and specialized knowledge for partitioning and offset management. The team lacks this expertise.
    - **Cost**: Self-hosting Kafka is labor-intensive; managed versions (Confluent) exceed the current budget.
    - **Over-engineering**: The 10x growth target (5k req/s) is well within the capabilities of Redis Streams. Moving to Kafka would be solving a scaling problem we do not yet have, while introducing a maintenance problem we cannot currently solve.
    - **Setup Time**: Learning and deploying a production-ready Kafka cluster would certainly exceed the 2-week value-delivery window.
