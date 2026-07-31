---
slug: adr-001-redis-streams
---
# ADR-001: Redis Streams over Kafka for notifications

**Context:** SaaS PM platform (85k MAU, 2M tasks/mo, 500 req/s peak, 6-person team, no infra engineer, Redis already in prod, no Kafka experience, 2-week delivery window, modest budget).
**Finding:** Chose Redis Streams for async notifications (email/webhook/WebSocket). Decisive reasons: (1) Kafka EOS is within-broker only — end-to-end exactly-once for external side effects needs idempotent consumers on either option (Confluent delivery-semantics docs); (2) Redis already operated, zero new infra; (3) load is orders of magnitude under single-node Redis; (4) Kafka ops burden exceeds team capacity. Billing exactly-once = at-least-once + event_id `ON CONFLICT DO NOTHING` dedup in Postgres; retries via XAUTOCLAIM idle-time backoff; DLQ stream.
**Source:** workdir/ADR-001-notification-architecture.md (trial-2); redis.io docs (streams, xautoclaim); kafka.apache.org/40 upgrade (KRaft prod-ready 3.3, ZK removed 4.0)
**Revisit trigger:** >100k msg/s sustained, durable event replay >days, many consumer groups, or Kafka Streams/ksqlDB — migrate behind enqueue_event() abstraction.

## Backlinks
- [Activity log 2026-07-31](../activity-log/2026/2026-07/2026-07-31.md) — ADR written this session
