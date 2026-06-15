# ADR-001: Notification Subsystem Architecture

## Status

Proposed

## Context

Our SaaS project-management platform currently processes notifications (emails and webhooks) synchronously inside the HTTP request cycle. At 85,000 monthly active users and a peak of ~500 req/s, this has become untenable:

- **Request timeouts**: Notification I/O blocks the response; average latency is 800 ms and spikes to 8 s during peak hours.
- **Silent failures**: Dropped messages when providers are unreachable. No retry or dead-letter mechanism exists.
- **Cascading failures**: Slow webhook endpoints have caused connection-pool exhaustion and taken down unrelated features twice this year.
- **No delivery guarantees**: Billing-critical events (trial expiration, payment failure) must be delivered exactly once, but the current system offers no such guarantee.

We need to decouple notification work from the request cycle, add retry with exponential backoff, and prepare for 10× traffic growth (≈5,000 req/s peak). Within two quarters we also plan to add real-time WebSocket push notifications.

**Team and infrastructure constraints**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer.
- Redis is already in production (sessions, rate limiting).
- No team member has production Kafka experience.
- The migration must start delivering value within two weeks.
- Budget is modest; managed Confluent Cloud is not affordable at full scale today.

## Decision

We will adopt **Redis Streams** as the notification backbone.

**Why Redis Streams is the right choice for this team and scale**

| Property | Requirement | Redis Streams | Apache Kafka |
|----------|-------------|---------------|--------------|
| **Throughput** | Peak 5,000 msg/s after 10× growth | >100,000 msg/s per node—ample headroom | Millions of msg/s per cluster—overkill |
| **Ordering** | FIFO per notification type | Guaranteed insertion order within a stream | Strong per-partition ordering |
| **Retention** | Hours to days for retry windows | Memory-bound; capped with `MAXLEN` | Disk-based; weeks to months by default |
| **Consumer groups** | Horizontal scaling of workers | Native (`XGROUP`, `XREADGROUP`, `XACK`) | Mature, automatic rebalancing |
| **Exactly-once semantics** | Required for billing events | At-least-once native; exactly-once requires application-level deduplication | Native exactly-once transactions (idempotent producer + consumer) |
| **Operational complexity** | Must be runnable by a generalist team | Low—same binary and runbook we already operate | High—ZooKeeper/KRaft, broker tuning, partition management, dedicated monitoring |
| **Time to production** | ≤ 2 weeks | Days | Weeks to months for a team without prior experience |
| **Budget** | Modest | Re-use existing Redis infrastructure | Self-hosted is labor-intensive; managed is excluded by budget |

Redis Streams satisfies every functional requirement at our scale while respecting the overriding organizational constraints: team size, existing expertise, timeline, and budget.

**Handling exactly-once for billing notifications**

True end-to-end exactly-once delivery is impossible without an idempotent sink; even Kafka guarantees exactly-once processing only inside its own topology. We will enforce billing exactly-once at the application layer, which is the pattern required at the delivery boundary regardless of broker choice:

1. **Idempotent consumers**: Each billing event carries a deterministic UUID. The consumer writes the UUID to PostgreSQL with a unique constraint before executing the notification. Duplicate deliveries become no-ops.
2. **Idempotency keys**: External API calls (email provider, webhooks) include the same UUID so that retries at the network layer are also safe.
3. **Ack-on-commit**: The consumer acknowledges the Redis stream entry (`XACK`) only after the PostgreSQL transaction commits. This keeps the at-least-once Redis guarantee aligned with durable deduplication state.

**Future WebSocket push**

Redis can also serve the planned real-time WebSocket layer (Pub/Sub or a dedicated stream per user session), avoiding a second infrastructure component.

## Consequences

### Pros

- **Operational simplicity**: The team already patches, backs up, and monitors Redis. Adding Streams is a configuration change, not a new system to learn.
- **Fast time-to-value**: We can have asynchronous notifications with retry running in production within days, well inside the two-week window.
- **Sufficient scale**: A single Redis node can handle more than an order of magnitude above our 10× target.
- **Consumer-group scaling**: We can add dedicated notification workers simply by spinning up new consumer-group members.
- **Budget fit**: Uses existing infrastructure. No new license or managed-service cost.
- **Unified real-time stack**: Redis Pub/Sub or Streams can power the WebSocket push feature scheduled for the next two quarters.

### Cons

- **Memory-bound retention**: Long-term replay is limited by RAM. We will cap stream lengths with `MAXLEN` (or `MAXLEN ~` for approximate trimming) and treat the stream as a transient work queue, not an event store. Deep historical audit trails must remain in PostgreSQL.
- **No native exactly-once**: Application-level deduplication is mandatory for billing events. If implemented incorrectly, duplicates are possible.
- **Less mature ecosystem**: Unlike Kafka, there is no rich connector ecosystem (e.g., Kafka Connect). Retry scheduling, dead-letter handling, and back-pressure logic must be built into the Python workers rather than configured declaratively.
- **Cluster scaling friction**: If we eventually outgrow a single Redis node, moving to Redis Cluster adds sharding complexity and requires re-evaluating stream topology.

## Alternatives Considered

### Apache Kafka

Kafka was rejected.

Kafka offers industry-leading throughput, disk-based retention, and native exactly-once transactions. For a much larger team or an event-sourcing architecture, it would be the default choice. However, for this organization its operational burden is disqualifying:

- **Operational complexity**: Self-hosted Kafka requires ZooKeeper or KRaft, careful broker tuning, partition planning, replication-factor management, and dedicated monitoring. A 6-person team with no Kafka experience and no infrastructure specialist would be taking on a high-risk operational tax.
- **Timeline mismatch**: A safe, production-ready Kafka deployment—self-hosted or evaluated managed options—cannot be completed, stabilized, and migrated within two weeks.
- **Budget mismatch**: Managed Confluent Cloud, which would remove the operational burden, is explicitly excluded by our modest budget.
- **Over-engineering at current scale**: Our 10× growth target (5,000 msg/s peak) is well within the comfortable operating range of a single Redis instance. Kafka’s million-msg/s ceiling solves a problem we do not have today and are unlikely to have within the planning horizon.

Therefore, we will proceed with **Redis Streams**.
