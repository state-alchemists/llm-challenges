---
slug: notification-architecture
---
# Notification Subsystem: Redis Streams Decision

**Context:** Chosen message backbone for the async notification subsystem (email, webhook, WebSocket push) on a 6-person SaaS team already running Redis.
**Finding:** Redis Streams selected over Apache Kafka. Rationale: existing Redis infra, zero Kafka ops experience, 2-week delivery constraint, current scale (~500 req/s) makes Kafka's throughput overkill. Exactly-once for billing handled at application layer (idempotent consumers + PostgreSQL dedup) rather than Kafka's transactional EOS.
**Source:** `ADR-001-notification-architecture.md`

## Backlinks
- [activity-log/2026/2026-07/2026-07-06](../activity-log/2026/2026-07/2026-07-06.md) — ADR written and decision recorded
