---
slug: trial-3-notification-adr
---
# Trial 3: Notification Architecture ADR

**Context:** This experiment evaluates architectural decision-making for a production SaaS notification subsystem.
**Finding:** Redis Streams chosen over Apache Kafka based on team constraints (6 engineers, no Kafka experience, existing Redis, modest budget).
**Source:** `workdir/ADR-001-notification-architecture.md`

## Summary

The system (85k MAU, 500 req/s peak, Python/Flask monolith) needs to decouple notification delivery from the HTTP request cycle. Redis Streams wins over Kafka because:
- Already running Redis in production (session, rate limiting)
- No team Kafka experience; 2-week delivery constraint
- Throughput well within Redis Streams' capability (5k events/s at 10x growth)
- Kafka's partitioning and infinite retention advantages are unnecessary at this scale
- Billing exactly-once handled via idempotency keys at the consumer layer

## Backlinks
- [root index](../index.md) — linked from project section
- [projects index](index.md) — listed as a project
- [2026-07-06 activity log](../activity-log/2026/2026-07/2026-07-06.md) — ADR written here
