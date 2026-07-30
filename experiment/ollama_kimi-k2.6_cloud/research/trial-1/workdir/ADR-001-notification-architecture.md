# ADR-001: Notification Architecture — Redis Streams

## Status

Proposed

## Context

Our SaaS project management platform (85K MAU, ~2M tasks/month, peak ~500 req/s) currently sends notifications (email, webhooks) synchronously inside the HTTP request cycle. This causes request timeouts (800ms average, 8s spikes), silent failures with no retry, cascading failures that exhaust connection pools, and zero delivery guarantees for billing-critical events.

We must decouple notification processing, add retry with exponential backoff, guarantee at-least-once delivery (and exactly-once for billing events), and lay groundwork for real-time WebSocket push within two quarters. The system must handle 10x traffic growth without re-architecting.

**Constraints:**
- Engineering team: 6 people (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already runs in production (sessions, rate limiting)
- No Kafka experience on the team
- Must deliver value within 2 weeks of setup/migration work
- Modest budget — managed Confluent Cloud is not viable at full scale today

## Decision

We will adopt **Redis Streams** as the message broker for the notification subsystem.

### Justification

| Criterion | Redis Streams | Apache Kafka | Assessment |
|-----------|--------------|--------------|------------|
| **Operational complexity** | Single Redis instance already in production; enabling Streams is a config change. No new deployment or networking topology. | Self-hosted Kafka requires ZooKeeper or KRaft, broker tuning, partition planning, and cluster monitoring. High operational surface area. | **Redis wins.** A 6-person team with no infra engineer cannot safely run self-hosted Kafka in 2 weeks. |
| **Time to value** | Can integrate with existing Python/Flask workers in days; team already knows Redis clients and monitoring. | Would require learning broker ops, client EOS semantics, and failure modes before going live. | **Redis wins.** The 2-week constraint rules out a new distributed system. |
| **Throughput** | Single-node Redis handles hundreds of thousands of messages/sec. Peak 500 req/s (and 10x growth to ~5,000 req/s) is well within headroom. | Millions of messages/sec with partitioning; massive overkill at our current scale. | **Both adequate.** Redis provides ample runway. |
| **Consumer groups** | Native consumer groups with simple ownership tracking; easy to reason about in Python. | Mature consumer groups with cooperative rebalancing; more powerful but more complex client behavior. | **Redis wins.** Simpler semantics reduce bug surface for a small team. |
| **Message retention** | Trim by length or time (e.g., 7–30 days). Retention is memory-bound, but notification payloads are small. | Disk-based, configurable retention from days to years; effectively unlimited. | **Adequate for Redis.** Notification streams do not require years of retention. |
| **Ordering guarantees** | Total order within a single stream. Partitioning by event type (e.g., `stream:billing`, `stream:webhooks`) preserves ordering per stream. | Ordered within a partition; total order requires a single partition (sacrificing parallelism) or application-level sequencing. | **Both adequate.** We will use separate streams per event type to preserve ordering where needed. |
| **Exactly-once semantics** | Natively at-least-once. Exactly-once requires application-level deduplication with idempotency keys (stored in Redis or PostgreSQL). | Native exactly-once semantics (idempotent producers + transactional consumers) via broker-side deduplication. | **Kafka is superior here, but** the client-side complexity of Kafka EOS is non-trivial and error-prone for teams without experience. We will achieve exactly-once for billing events with application-level idempotency keys, a well-understood pattern. |
| **Cost** | Uses existing Redis infrastructure. Negligible marginal cost. | Self-hosted: server/ops cost. Managed: exceeds modest budget. | **Redis wins.** Budget constraint eliminates managed Kafka; self-hosted ops cost is too high. |

**Summary:** Redis Streams satisfies our throughput, ordering, and consumer-group requirements while meeting the hard constraints of team size, timeline, and budget. The one area where Kafka is objectively stronger — native exactly-once semantics — is mitigated by implementing idempotent consumers with deduplication keys, which is safer for this team than attempting to operate an unfamiliar distributed broker under a 2-week deadline.

## Consequences

### Pros
- **Fast migration:** Can move notifications off the synchronous path and into background workers within the 2-week window.
- **Operational continuity:** Leverages existing Redis expertise, runbooks, and monitoring.
- **Low cost:** No new infrastructure spend; uses the same Redis nodes already paying for sessions and rate limiting.
- **Simpler mental model:** Consumer groups and stream offsets are easier to debug than Kafka partition rebalancing and consumer lag.
- **Dual-use foundation:** Redis Pub/Sub (or Streams consumers) can later feed WebSocket push notifications without introducing a third system.

### Cons
- **Application-level exactly-once:** Billing notifications require idempotency keys stored in a deduplication table (Redis SET with TTL or PostgreSQL unique constraints). This adds client complexity that Kafka would handle broker-side.
- **Memory-bound retention:** Very long retention or an unexpected message volume surge could pressure memory. We will set sensible max-length trims and alert on memory usage.
- **Smaller ecosystem:** Fewer off-the-shelf connectors and stream-processing libraries than Kafka Connect / Kafka Streams.
- **Future re-evaluation ceiling:** If traffic grows far beyond 10x or retention needs expand to months/years, we may need to migrate to Kafka. This is acceptable — the ADR is not “Kafka forever,” it is “Kafka is the wrong tool for this team today.”

## Alternatives Considered

### Apache Kafka

We rejected self-hosted Kafka because:

1. **Operational burden:** Running even a minimal 3-broker cluster with ZooKeeper or KRaft requires expertise in partition rebalancing, ISR management, and failure recovery that the team does not possess today.
2. **Timeline risk:** A production-hardened Kafka deployment, including client library integration for exactly-once semantics, cannot be completed safely in 2 weeks by a team with no prior experience.
3. **Budget:** Managed Kafka (Confluent Cloud, Amazon MSK) exceeds our modest budget at scale. Self-hosted is the only viable path, and it conflicts with constraints 1 and 2.
4. **Over-capacity:** Kafka’s primary advantage — massive throughput and long-term retention — is not a near-term need. We would be paying complexity tax for headroom we do not yet require.

We acknowledge that Kafka is the superior technology for large-scale event streaming in the abstract. Under our specific constraints (team size, expertise, budget, deadline), it is the higher-risk, lower-return choice.
