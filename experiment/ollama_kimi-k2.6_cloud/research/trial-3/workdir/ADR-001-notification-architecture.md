# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users and generates ~2 million tasks per month, with peak traffic of ~500 requests per second during business hours. Notifications (emails and webhooks) are currently dispatched synchronously inside the HTTP request cycle, causing:

- **Request timeouts**: Average notification latency of 800ms, spiking to 8s during peak hours.
- **Silent failures**: No retry mechanism when email providers or webhook endpoints are unavailable.
- **Cascading failures**: Slow downstream endpoints have caused connection pool exhaustion, impacting unrelated features.
- **No delivery guarantees**: Billing-critical events (e.g., "trial expired", "payment failed") lack exactly-once semantics.

We must decouple notification delivery from the request cycle, introduce retry with exponential backoff, guarantee at-least-once delivery (with exactly-once for billing events), and architect for 10x traffic growth without requiring another migration.

**Constraints:**
- Engineering team of 6 (3 senior, 3 mid-level), with no dedicated infrastructure engineer.
- Redis is already in production (session storage, rate limiting).
- No prior Kafka experience on the team.
- Setup and migration must deliver value within 2 weeks.
- Budget is modest; managed Kafka (e.g., Confluent Cloud) at full projected scale is not viable today.

## Decision

We will adopt **Redis Streams** as the message backbone for the notification subsystem.

**Justification:**

1. **Operational leverage.** Redis is already a production dependency. Adding Streams requires no new infrastructure, monitoring stack, or operational runbook. Kafka, by contrast, would demand learning KRaft/ZooKeeper, partition rebalancing, broker tuning, and a new failure domain—none of which our team can sustainably own without dedicated infrastructure support.

2. **Time-to-value.** Redis Streams can be integrated into our existing Python/Flask monolith within days. We can provision consumer groups, implement exponential-backoff retry, and start relieving request-cycle pressure well inside the 2-week constraint. A production-grade self-managed Kafka deployment would consume the entire window just in setup and testing.

3. **Throughput is sufficient.** At ~500 req/s peak today and a 10x target of ~5,000 req/s, Redis Streams is well within operational limits. A single Redis instance can sustain tens of thousands of messages per second; scaling reads horizontally via consumer groups gives us headroom without re-architecting.

4. **Consumer groups and ordering.** Redis Streams provides native consumer groups with automatic claim and failover semantics. For our use case—per-user or per-task notification streams—partition-level ordering is not required, but stream-level ordering within a given context is achievable by using targeted stream keys.

5. **Exactly-once for billing events.** Redis Streams does not offer built-in exactly-once semantics. We will implement exactly-once delivery for billing notifications **at the application layer** by:
   - Publishing billing events with unique idempotency keys.
   - Tracking processed keys in PostgreSQL (which we already operate) using atomic upserts.
   - Wrapping consumer acknowledgment and idempotency-key persistence in a single database transaction.
   This is a pragmatic, well-understood pattern that trades infrastructure complexity for straightforward application code.

6. **Path to WebSocket push.** Redis is already used for pub/sub patterns in many real-time stacks. Reusing the same Redis cluster for Streams (async queueing) and pub/sub (WebSocket fan-out) keeps our infrastructure footprint minimal when we add real-time notifications in the next two quarters.

## Consequences

### Pros

- **Minimal operational overhead:** Reuses existing Redis expertise, monitoring, and failover procedures.
- **Fast migration:** Can ship value and relieve request-cycle pressure inside the 2-week deadline.
- **Low hardware footprint:** No additional brokers or clusters; horizontal scaling of consumers is straightforward.
- **Flexible retention:** Stream trimming (`XTRIM`, `MAXLEN`) gives us simple, policy-based message TTL without complex log-compaction semantics.
- **Unified Redis footprint:** Future real-time WebSocket pub/sub can run on the same cluster.

### Cons

- **Durability trade-off:** Redis persistence (AOF/RDB) is not as robust as Kafka’s replicated commit log. A catastrophic, simultaneous failure of primary and replica could lose unprocessed messages. We will mitigate this with AOF `everysec` and rapid replica promotion.
- **Memory-bound retention:** Very large backlogs or long retention periods are constrained by memory. We will enforce aggressive `MAXLEN` policies and archive completed billing events to PostgreSQL.
- **Exactly-once complexity:** The burden of deduplication falls on application code rather than the streaming platform. We must ensure idempotency-key table is well-indexed and purged periodically.
- **Consumer group maturity:** Redis Streams consumer-group rebalancing is less battle-tested than Kafka’s. We will monitor consumer lag and implement health-check-driven restarts to avoid stuck consumers.
- **Ecosystem gaps:** There is no native equivalent to Kafka Connect or MirrorMaker. Integrations with third-party systems (e.g., data warehouse sinks) will require custom consumers.

## Alternatives Considered

### Apache Kafka

We rejected Apache Kafka because the operational and expertise costs outweigh the architectural benefits for our current stage.

- **Operational complexity:** Self-managed Kafka requires broker tuning, KRaft or ZooKeeper coordination, partition management, and careful rebalancing during scaling events. Our 6-person team has no Kafka experience and no dedicated infrastructure engineer to absorb this burden.
- **Setup timeline:** A production-ready Kafka cluster (even a modest 3-broker setup) with client libraries, consumer group testing, failure-injection validation, and runbook creation would exceed our 2-week time-to-value constraint.
- **Budget constraints:** Managed Kafka (Confluent Cloud, MSK) would solve operational concerns but at a cost incompatible with our modest budget at 10x scale.
- **Advantages we cannot exploit:** Kafka’s superior exactly-once producer semantics, log compaction, and ecosystem (Connect, MirrorMaker) are genuinely powerful, but they solve problems we do not yet have at a price (time, money, complexity) we cannot afford. If we outgrow Redis Streams, Kafka remains a natural migration path once we have the staffing and budget to operate it.
