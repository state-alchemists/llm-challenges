# ADR-001: Notification Subsystem — Redis Streams over Apache Kafka

## Status

Proposed

## Context

Our SaaS project management platform (85k MAU, ~2M tasks/month, ~500 req/s peak) handles notifications — emails and webhooks on task updates, assignments, and completions — synchronously inside the HTTP request cycle. This causes request timeouts (800ms avg, 8s spikes), silent failures with no retry or dead-letter queue, cascading connection-pool exhaustion from slow webhook endpoints, and no delivery guarantees for billing-critical events.

We must decouple notification dispatch from the request cycle, add retry with exponential backoff, guarantee at-least-once delivery (exactly-once where feasible for billing), support real-time WebSocket push within two quarters, and absorb 10x traffic growth without re-architecting.

Key constraints:

- **Engineering team**: 6 people (3 senior, 3 mid-level); no dedicated infrastructure engineer.
- **Redis already in production** for sessions and rate limiting.
- **No Kafka experience** on the team.
- **2-week ceiling** before the change delivers value.
- **Modest budget** — managed Confluent Cloud at scale is not affordable today.

## Decision

**We will use Redis Streams as the notification subsystem's message backbone.**

Redis Streams provides consumer-group semantics, persistent (AOF/RDB-backed) message storage, per-stream strict ordering, and throughput well beyond our current and projected scale — all on infrastructure we already operate. The operational simplicity and time-to-value are decisive given our team size, skill set, and delivery constraint.

## Consequences

### Pros

1. **Immediate time-to-value.** Redis is already running in production with operational runbooks. Adding Streams requires enabling a data structure, not deploying a new distributed system. We can ship async dispatch within the 2-week window.

2. **Sufficient throughput.** Redis Streams handles hundreds of thousands of messages per second on a single instance. Our peak of ~500 req/s with a 10x growth target (~5k msg/s) is two orders of magnitude below Redis's ceiling. No sharding or clustering required at this scale.

3. **Consumer groups built-in.** `XGROUP`, `XREADGROUP`, and `XACK` provide partitioned, load-balanced consumption with delivery tracking — the same fundamental model Kafka consumer groups offer, adequate for our fan-out patterns (email worker, webhook worker, future WebSocket worker).

4. **Per-stream ordering.** All notifications for a given entity type (e.g., `billing`, `task-update`) are strictly ordered within a single stream. This is sufficient for our use case, where ordering matters within a category but not across all notification types globally.

5. **Operational simplicity.** One fewer distributed system to deploy, monitor, certificate-rotate, and on-call for. Redis is already in our incident response playbooks. A 6-person team with no dedicated infra engineer cannot afford to babysit a Kafka cluster.

6. **Natural path to WebSocket push.** Redis Pub/Sub is the canonical transport for real-time fan-out in Python/Flask ecosystems. Sharing the same Redis instance for Streams (durable, queued work) and Pub/Sub (ephemeral, real-time push) keeps the infrastructure footprint flat when we add WebSocket delivery.

7. **Cost.** No additional infrastructure spend at current scale. Self-managed Kafka would require at least 3 broker nodes (plus ZooKeeper or KRaft controllers) even for a minimal deployment — a material budget increase for a modest-run-rate SaaS.

### Cons

1. **Exactly-once is application-level, not platform-level.** Redis Streams provides at-least-once delivery via `XREADGROUP` + `XACK`. A consumer crash after processing but before `XACK` causes redelivery. For billing notifications, we will implement idempotent consumers using a PostgreSQL dedup table (notification ID → processed flag) inside a transaction, achieving effectively-once semantics. This is more work than Kafka's transactional producer/consumer API but is straightforward to implement correctly within our 2-week window.

2. **Message retention is memory-bound.** Redis persists to disk via AOF or RDB snapshots, but the active dataset lives in memory. Long retention windows (weeks) at high volume become expensive. We will cap retention with `MAXLEN` (~100k entries per stream, covering ~24h of backlog at 10x scale) and archive processed events to PostgreSQL for audit/history. This is an explicit trade: we trade Kafka's multi-terabyte disk-based retention for operational simplicity, accepting that our message bus is a short-horizon buffer, not a long-term store.

3. **No native partitioning across multiple keys.** Kafka partitions a single topic across N brokers for parallelism; Redis Streams parallelism comes from multiple streams or consumer-group partitions within a single stream. For our volume, a single stream per domain (`notifications:billing`, `notifications:webhook`, `notifications:email`) with consumer groups provides all the parallelism we need, but this architecture does not generalize to a firehose of millions of events across dozens of services. If we reach that scale, we will reconsider — but that is a problem we do not have today.

4. **Monitoring and tooling are thinner.** Kafka has a rich ecosystem of UI consoles, schema registries, and observability tooling. Redis Streams tooling exists (e.g., `redis-cli XINFO`, various open-source dashboards) but is less mature. We accept this: our team can instrument Redis stream lag and consumer-group backlog with a few Prometheus metrics and a Grafana dashboard, which is sufficient for our operational needs.

## Alternatives Considered

### Apache Kafka

Kafka is the industry-standard distributed event platform and would serve our notification needs well on purely technical grounds:

| Property | Kafka | Redis Streams |
|---|---|---|
| Throughput | Millions of msg/s per cluster | Hundreds of thousands of msg/s per instance |
| Ordering | Strict per-partition | Strict per-stream |
| Retention | Disk-based, configurable (days–weeks) | Memory + AOF/RDB, `MAXLEN`-capped |
| Consumer groups | First-class, rebalancing protocol | `XGROUP`/`XREADGROUP`, adequate for our scale |
| Exactly-once | Idempotent producer + transactions | At-least-once; exactly-once via application-level dedup |
| Operational complexity | High (brokers, controllers, partition management) | Low (already operated) |
| Time to first value | Weeks (new infrastructure, no team experience) | Days (existing infrastructure, familiar tooling) |

We reject Kafka at this time for three reasons:

1. **Operational cost exceeds our capacity.** A 6-person team with no Kafka experience and no dedicated infra engineer cannot reliably operate a Kafka cluster. The learning curve for partition rebalancing, controller failures, and offset management is steep; misoperation risks exactly the kind of downtime we are trying to prevent.

2. **The 2-week delivery constraint is non-negotiable.** A minimal Kafka deployment (3 brokers, topic provisioning, security, monitoring) plus consumer/producer integration in an unfamiliar codebase will take 4–6 weeks with this team. Redis Streams integration with our existing Flask monolith is a 3–5 day change.

3. **Budget.** Managed Kafka (Confluent Cloud, AWS MSK) eliminates the ops burden but at a cost that our modest budget cannot sustain at projected volume. Self-managed Kafka shifts the cost from dollars to engineer-hours we do not have.

Kafka remains a viable future option. If our notification volume grows beyond Redis's comfortable memory envelope, or if we adopt an event-sourcing pattern requiring multi-day retention across many consumer teams, we will evaluate Kafka again — with the operational headcount and budget to match.

### Other alternatives considered and rejected

- **PostgreSQL SKIP LOCKED (queue via DB)**: Already our primary datastore. Using it as a queue re-introduces coupling between the transactional DB and the async workload, and does not support fan-out to multiple consumer groups. Rejected.

- **RabbitMQ / AWS SQS**: Viable but introduces a new operational dependency without the multi-use advantage of Redis (which also serves sessions, rate limiting, and future WebSocket pub/sub). Rejected on infrastructure-minimization grounds.

- **Celery with Redis broker**: Celery adds a heavy abstraction layer and does not provide the consumer-group semantics or streaming semantics we need for ordered, partitioned delivery. It also couples task definitions to the Celery API, making future consumer implementations in other services awkward. Rejected.