# ADR-001: Notification Subsystem Message Broker Selection

## Status

Proposed

## Context

Our SaaS project management platform (~85,000 MAU, ~2M tasks/month, 500 req/s peak) currently handles notifications synchronously inside the HTTP request cycle. This causes request timeouts (avg 800ms, spikes to 8s), silent failures, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical notifications.

We need to decouple notifications from the request cycle with retry logic, at-least-once delivery (exactly-once for billing events), and capacity for 10x growth. We plan WebSocket push within two quarters.

**Constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer
- No Kafka experience on the team
- 2-week maximum setup/migration window before delivering value
- Modest budget (Confluent Cloud at full scale is not affordable)
- Redis already runs in production for sessions and rate limiting
- Exactly-once semantics required for billing notifications

## Decision

**Choose Redis Streams.**

The combination of no prior Kafka experience, a 2-week delivery constraint, an existing Redis deployment, and a modest budget makes Redis Streams the pragmatic choice. Redis Streams provides sufficient throughput for our current and projected 10x growth (500 req/s × 10 = 5,000 req/s; Redis Streams handles 100K–1M events/sec on commodity hardware), operational familiarity, and a gentler learning curve. The team can implement, debug, and extend this system without external expertise or significant infrastructure changes.

Exactly-once semantics for billing notifications will be achieved through application-level idempotency keys stored in Redis (a natural fit given the existing Redis footprint).

## Consequences

### Pros

| Property | Redis Streams | Kafka (comparison) |
|---|---|---|
| **Operational complexity** | Low — team already runs Redis | High — requires ZooKeeper/KRaft, partition planning, replication factor tuning |
| **Time to value** | ~3–5 days POC with existing Redis | ~2+ weeks just to reach production readiness without prior experience |
| **Infrastructure cost** | Zero new infrastructure | 3+ new servers for a minimally HA cluster |
| **Throughput** | 100K–1M events/sec (sufficient for 10x growth target) | Millions/sec (overkill for current scale) |
| **Existing knowledge** | Team knows Redis | No Kafka expertise |
| **Scaling** | Vertical (vertical is sufficient for projected load) | Horizontal (complex but handles extreme scale) |

Additional benefits:
- **Consumer groups (XREADGROUP/XACK)** provide the retry and acknowledgment model we need
- **Message retention** configurable up to 512GB per stream (exceeds our needs at current growth rates)
- **Disk-backed** streams persist data to AOF, providing durability without a separate message broker
- **Existing Redis footprint** means monitoring, backups, and operational runbooks already exist
- **WebSocket readiness** — Redis pub/sub can serve real-time push notifications within the same system

### Cons

| Concern | Mitigation |
|---|---|
| **Not true exactly-once** — Redis Streams offers at-least-once only | Implement idempotency keys (billing event ID stored in Redis with TTL); discard duplicates on consumption |
| **Scaling ceiling** — vertical scaling has practical limits | At 500 req/s × 10x = 5,000 req/s, we are orders of magnitude below Redis Streams' ceiling; migrate to Kafka if/when that becomes necessary |
| **No native dead-letter queue** | Build with stream consumer groups: failed messages after N retries move to a dedicated `notifications.dlq` stream |
| **Memory pressure** | Configure `MAXLEN` on streams to cap memory; retention tuned to SLAs (~7 days covers retry windows) |
| **Multi-consumer fan-out** — if the same notification needs email + webhook + push, consumer must route manually | Single notification handler reads from stream and fans out internally; different delivery channels are separate worker threads, not separate consumer groups competing for messages |

## Alternatives Considered

### Apache Kafka

Kafka offers superior throughput (millions of events/sec), true exactly-once semantics via Kafka Transactions, mature consumer group offset management, and indefinite message retention without memory pressure. It is the industry standard for event streaming at scale.

However, for our constraints it is not the right choice:

- **No team experience.** Kafka has a steep operational learning curve. Without prior expertise, a 2-week deadline is unrealistic for a production-ready deployment. Misconfigurations (partition counts, replication factor, retention settings) cause production incidents.
- **Operational overhead.** A minimally HA Kafka deployment requires at minimum 3 brokers plus ZooKeeper (or KRaft) — sizing, monitoring, and recovery procedures are non-trivial for a team of 6 without a dedicated infrastructure engineer.
- **Cost.** Self-managed Kafka on AWS at HA requires 3+ `r5.xlarge` instances minimum (~$1,500–3,000/month). This exceeds a modest budget.
- **Over-engineering.** At 500 req/s with a 10x target of 5,000 req/s, we are 200–2000× below Kafka's practical floor. We would pay the operational complexity cost without needing the scale that justifies it.

Kafka would be the correct choice if: scale reached 100K+ events/sec, multiple teams needed independent consumers, or we had dedicated infrastructure engineers and a longer migration window.

### Rejected Options (Briefly)

| Option | Reason for Rejection |
|---|---|
| **Amazon SQS/SNS** | Adds a new managed service with its own pricing model; requires IAM, VPC endpoints, and SDK integration; no local development story (always cloud) |
| **RabbitMQ** | Operational overhead comparable to Kafka with less modern protocol support; no compelling advantage over Redis Streams given existing Redis investment |
| **Build our own queue in PostgreSQL** | Current database is already a single primary + one read replica; polling-based notification workers would add load to the primary and hit capacity limits at peak |

## Recommendation Summary

Implement the notification subsystem on **Redis Streams**. The team will ship production-ready async notifications within 1 week, using existing Redis infrastructure, with application-level idempotency for billing events. When/if throughput demands exceed ~50,000 events/sec or multiple teams require independent event consumption, re-evaluate Kafka with the operational experience gained from running Redis Streams in production.
