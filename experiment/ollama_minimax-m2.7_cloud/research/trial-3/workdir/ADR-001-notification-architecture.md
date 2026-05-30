# ADR-001: Notification Subsystem Architecture

## Title
Choose Redis Streams over Apache Kafka for the Notification Subsystem

## Status
**Proposed**

## Context

The notification module currently executes synchronously inside the HTTP request cycle, causing request timeouts (avg 800ms, peaks at 8s), silent failures on downstream errors, cascading failures that brought down unrelated features, and no delivery guarantees for billing-critical events.

We need to decouple notifications from the request cycle with async processing, exponential backoff retry, at-least-once delivery for billing events, exactly-once where feasible, and capacity to handle 10x traffic growth (from 500 req/s to ~5,000 req/s peak). The team is 6 people with no dedicated infrastructure engineer, no Kafka experience, and a 2-week maximum setup window. We already run Redis for session storage and rate limiting.

## Decision

**Choose Redis Streams.**

Redis Streams provides sufficient throughput, mature consumer group semantics, and operational simplicity that matches our team constraints. The existing Redis infrastructure means zero incremental operational cost and no new systems to maintain.

### Technical Justification

**Throughput:** At 500 req/s current peak (5,000 req/s at 10x growth), Redis Streams comfortably handles 100,000–500,000 events/second per node. Kafka's millions/s throughput is overkill for our scale and adds operational complexity we don't need.

**Ordering Guarantees:** Redis Streams guarantees ordering within a consumer group and per-stream. For notification ordering requirements (e.g., task created before task assigned), this is sufficient. Kafka offers stronger per-partition ordering but at higher operational cost.

**Message Retention:** Redis Streams retains messages via `MAXLEN` or memory-based eviction. For our billing notification requirement, we can configure retention long enough to support deduplication windows (24–72 hours is typical for exactly-once patterns).

**Consumer Groups:** Redis Streams consumer groups (`XREADGROUP`, `XACK`) provide mature group semantics with per-message acknowledgment, dead-letter handling via `XPENDING`, and automatic load balancing across consumers. This matches Kafka consumer groups functionally for our use case.

**Exactly-Once Semantics:** Redis Streams does not provide native exactly-once delivery. However, for billing notifications, we can achieve exactly-once semantics via:
- Idempotent producers using notification IDs (stored in Redis with TTL)
- Consumer-side deduplication using the same ID
- This pattern is well-documented and matches what we'd need to implement for Kafka anyway

**Operational Complexity:** Redis Streams requires no new infrastructure—it's already running. Configuration is via `CONFIG SET` commands. Monitoring uses existing Redis tooling. Kafka requires ZooKeeper/KRaft, partition planning, replication factor decisions, broker monitoring, and schema registry. For a 6-person team with no Kafka experience, this difference is decisive.

**Setup Time:** Redis Streams proof-of-concept takes hours, production implementation days. Kafka cluster setup alone typically takes 1–2 weeks for a team without experience, plus additional time for consumer group patterns and monitoring.

## Consequences

### Benefits of Redis Streams

1. **Zero incremental infrastructure** — We already run Redis; Redis Streams is enabled via configuration
2. **Familiar operational model** — The team already monitors and maintains Redis
3. **Fast time-to-value** — Production-ready implementation in under 2 weeks
4. **Consumer groups with ACK semantics** — `XREADGROUP` + `XACK` provides reliable delivery tracking
5. **Dead-letter handling** — `XPENDING` exposes messages that failed or timed out for manual intervention
6. **Built-in persistence** — AOF or RDB persistence protects against Redis restarts
7. **WebSocket readiness** — Redis pub/sub or Streams can serve as the real-time notification backbone when we add WebSocket support in 2 quarters
8. **Sufficient throughput** — 100k–500k events/second comfortably handles 10x growth with room to spare

### Drawbacks and Mitigations

1. **No native exactly-once** — Mitigation: idempotent producers with deduplication keys stored in Redis (same Redis instance, no new infrastructure)
2. **Memory-bound retention** — Very long retention (weeks) could be costly; mitigation: configure `MAXLEN~` for approximate retention matching our deduplication window needs (24–72 hours typically sufficient)
3. **Single-node throughput ceiling** — At extreme scale (500k+ req/s), Redis single-node becomes a bottleneck; mitigation: Redis Cluster can distribute streams across nodes, and our 10x target (5k req/s) is well within single-node capacity
4. **Less mature consumer group rebalancing** — Kafka's partition rebalancing is more sophisticated; mitigation: for our scale, Redis Streams consumer groups are sufficient, and `XGROUP CREATECONSUMER` handles sticky sessions well

## Alternatives Considered

### Apache Kafka

**Rejected because:**

- **Operational complexity** — Kafka requires cluster management (broker configuration, partition assignment, replication factor), ZooKeeper or KRaft for metadata, and schema registry for serialization. For a team with no Kafka experience, production-ready deployment takes 4–8 weeks minimum, not 2.
- **Infrastructure cost** — Even self-managed Kafka on AWS requires 3+ brokers for HA, plus ZooKeeper nodes or KRaft storage. This is significant compute cost we don't need at our scale.
- **Over-engineering** — Kafka's strengths (millions of events/second, cross-datacenter replication, complex stream processing) are unnecessary for 500–5,000 req/s. We would pay the operational complexity cost without receiving proportional benefit.
- **Team ramp-up time** — No one on the team has Kafka production experience. Debugging consumer group issues, partition skew, or replication lag would consume engineering time we don't have.
- **Managed alternatives exceed budget** — Confluent Cloud or Amazon MSK at our scale is cost-prohibitive on a modest budget. Self-managed is the only option, which adds operational burden.
- **Same exactly-once limitation** — Kafka's exactly-once semantics (`transaction.idempotent.enable`) also requires application-level deduplication for billing events. The complexity difference between Kafka + deduplication and Redis Streams + deduplication is negligible.

**When Kafka would be the right choice:** If we had a dedicated platform/infrastructure team, needed cross-datacenter replication, required Kafka Streams for complex event processing, or had 10x higher throughput (500k+ events/second), we would revisit this decision.

### Redis Streams was chosen over Kafka because:

1. **Matches team constraints** (no dedicated infra engineer, no Kafka experience, 2-week deadline)
2. **Leverages existing infrastructure** (no new systems to operate)
3. **Provides sufficient guarantees** (at-least-once with consumer groups, exactly-once via idempotent producers for billing)
4. **Handles our scale comfortably** (10x growth target is well within Redis Streams capacity)
5. **Enables future WebSocket work** (same Redis instance can serve pub/sub for real-time notifications)

## Resolution

Implement the notification subsystem using Redis Streams with the following architecture:

- **Producers:** Flask app publishes notification events to `XADD` with notification IDs for idempotency
- **Consumer group:** `XREADGROUP` for distributed consumption across worker processes
- **Dead-letter:** Failed messages (after max retries) moved to a separate stream (`notifications.dlq`) for manual review
- **Exactly-once for billing:** Producer stores `notification_id → delivered` in Redis with 48-hour TTL; consumer checks before processing
- **Monitoring:** Redis `XPENDING` and `XINFO` commands for queue depth and consumer lag alerting