# ADR-001 — Adopt Redis Streams for the Asynchronous Notification Subsystem

**Status:** Proposed

## Context

Our SaaS project-management platform serves 85,000 monthly active users and creates approximately two million tasks per month. Notification delivery—emails and webhooks triggered by task updates, assignments, and completions—is currently executed synchronously inside the Flask HTTP request cycle.

This design has become a critical bottleneck:

- **Latency**: Average notification latency is 800 ms, with spikes to 8 s during peak hours (~500 req/s).
- **Reliability**: There is no retry mechanism. If an email provider or webhook endpoint is down, the notification is silently dropped.
- **Resilience**: Two production incidents this year occurred when a slow webhook endpoint exhausted the connection pool, causing cascading failures across unrelated features.
- **Delivery guarantees**: Billing-critical events (trial expiration, payment failure) must be delivered exactly once; the current system offers no such guarantee.

We must decouple notification dispatch from the HTTP request path, introduce retry with exponential backoff, and satisfy at-least-once delivery for general events and exactly-once semantics for billing events. Within two quarters we also plan to add real-time WebSocket push notifications, and we need an architecture that can absorb roughly 10× traffic growth without a second migration.

Team and operational constraints bind the solution space:

- Engineering team of six (three senior, three mid-level) with **no dedicated infrastructure engineer**.
- Redis is already deployed in production for session storage and rate limiting.
- **No team member has operational experience with Apache Kafka**.
- Migration and production-ready setup must fit inside **two weeks**.
- Budget is modest; **managed Confluent Cloud is not affordable** at target scale.

## Decision

We will use **Redis Streams** as the message transport for the notification subsystem.

Redis Streams satisfies our throughput requirements, provides adequate ordering and consumer-group semantics for our scale, and—crucially—fits inside our operational envelope. Because our consumers ultimately deliver to external, idempotent-agnostic systems (SMTP gateways and customer webhook URLs), even a platform with native exactly-once processing would require application-level deduplication. We will therefore implement exactly-once delivery for billing events by attaching deterministic idempotency keys to every billing notification and recording processed keys in our existing PostgreSQL primary before performing any external side effect. This pattern is well understood, reliable, and avoids introducing a second persistence stack solely for consumer offset management.

## Consequences

### Positive

- **Time-to-value**: Because Redis is already running, we can complete the migration within days rather than weeks, satisfying the two-week deadline.
- **Zero additional infrastructure cost**: No new EC2 instances, no extra managed-service bill, and no ZooKeeper/KRaft ensemble to maintain.
- **Low operational risk**: The team already operates Redis for sessions and rate limiting. Monitoring, backup, and failover procedures are in place.
- **Throughput headroom**: Redis Streams routinely handles 100,000+ messages per second on a single instance. Our peak of 500 req/s—even under a 10× growth scenario—leaves ample margin before sharding becomes necessary.
- **Synergy with WebSocket push**: Redis Pub/Sub coexists in the same deployment. The planned WebSocket push feature can reuse the existing Redis cluster, avoiding a future infrastructure pivot.
- **Immediate resilience**: Moving dispatch into an async worker pool eliminates the synchronous blocking that causes request timeouts and connection-pool exhaustion.

### Negative

- **Memory-bound retention**: Redis is memory-first. Stream depth must be capped (via `MAXLEN` or `XTRIM`), so long-term audit trails must be archived to PostgreSQL or object storage if required.
- **Application-level exactly-once burden**: Unlike Kafka, Redis Streams offers no native exactly-once semantics. Consumer bugs or reprocessing during a redeploy could duplicate a billing notification unless the idempotency table is consulted rigorously. This shifts correctness responsibility from the broker to application code.
- **Consumer group maturity**: Redis consumer groups support automatic failover and pending-list reclamation, but the rebalancing protocol is less mature than Kafka’s. Under Redis Cluster, large-scale rebalancing has sharp edges that we have not yet exercised.
- **Horizontal scaling ceiling**: While a single Redis node absorbs our projected 10× load comfortably, sustained growth beyond ~50,000 messages per second or shard-per-stream sharding would eventually force a re-evaluation.
- **Approximate trimming**: Stream length caps are approximate when specified by count, and time-based expiry (`MINID`) requires explicit housekeeping. We must monitor memory and adjust policies proactively.

## Alternatives Considered

### Apache Kafka

Kafka was rejected as the primary substrate for this migration.

- **Operational complexity**: A self-hosted Kafka deployment on AWS requires provisioning brokers, configuring replication, managing either ZooKeeper or KRaft, tuning partition counts, and establishing a monitoring baseline. Our six-person team has zero prior operational experience with Kafka. Given the two-week setup constraint and the absence of a dedicated infrastructure engineer, the risk of a misconfigured cluster causing data loss or prolonged outage outweighed Kafka’s technical advantages.
- **Exactly-once semantics**: Kafka offers idempotent producers and transactional consumption, which would simplify in-pipeline exactly-once guarantees. However, because our final destinations are external SMTP and HTTP endpoints that do not themselves participate in distributed transactions, we would still need application-level idempotency keys to guard against redelivery during consumer restarts or retries. The marginal safety gain of Kafka transactions over Redis Streams plus PostgreSQL deduplication was therefore smaller than it first appeared.
- **Cost and setup time**: Without a Confluent Cloud budget, we would need to run our own cluster. Initial provisioning, security-group configuration, cross-AZ replication, and failover testing would consume the entire two-week window—or exceed it—before delivering any notification reliability improvements.
- **Retention model**: Kafka’s durable, disk-backed log with configurable retention is undeniably superior for long-term replay and audit. Our notification retry window is minutes to hours, not days, so we do not currently exploit that advantage.

Kafka would become the preferable choice if our sustained throughput exceeds the practical limit of a Redis Cluster, if regulatory requirements mandate multi-day immutable log replay without external archival, or if we hire dedicated platform-engineering staff capable of operating a self-managed Kafka estate.
