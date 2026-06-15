# Notification Architecture Decision — Redis Streams over Kafka

**Date**: 2026-06-15
**Context**: SaaS project management platform (85K MAU, ~500 req/s peak) decoupling synchronous notifications into an async broker.

## Decision

Redis Streams chosen over Apache Kafka for the notification subsystem. Key reasons:

1. **Operational fit**: Redis already in production; team has no Kafka experience and no dedicated infra engineer.
2. **Time to value**: Redis Streams can ship in ~10 days vs. 2+ weeks for Kafka infrastructure alone.
3. **Throughput headroom**: 5,000 req/s target is 2 orders of magnitude below Redis Streams' ~100K msgs/s ceiling.
4. **Exactly-once for billing**: Achieved via application-layer idempotency keys in Postgres (same pattern Stripe uses for webhooks).
5. **Reversible**: Redis Streams today do not block introducing Kafka as a second tier later.

## Risks Accepted

- Single-node Redis is a SPOF (same as existing session store risk); Redis Sentinel/Cluster planned as follow-up.
- No native multi-DC replication; revisit if multi-region is required.
- Stream memory management requires `MAXLEN` trimming and monitoring.

## Cross-links

- ADR document: `ADR-001-notification-architecture.md` (in workdir, not journal)

## Backlinks

- [2026-06-15 activity log](../activity-log/2026/2026-06/2026-06-15.md) — decision recorded here