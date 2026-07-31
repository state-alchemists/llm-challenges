---
slug: notification-architecture
---
# Notification Subsystem Architecture Decision

**Context:** SaaS project management platform (85K MAU, 500 req/s peak) needs to decouple synchronous notifications from the HTTP request cycle. Team of 6, no infra engineer, already runs Redis, 2-week delivery deadline.
**Finding:** Redis Streams chosen over Apache Kafka. Redis is already in production, team knows it, setup is days not weeks, and throughput (100K+ msg/s) far exceeds 10× growth target. Exactly-once for billing achieved via idempotent-consumer pattern (PostgreSQL dedup table), which is the same pattern needed on top of Kafka for external side effects.
**Source:** ADR-001-notification-architecture.md, system_context.md

## Backlinks
- [activity-log/2026/2026-07/2026-07-31.md](../activity-log/2026/2026-07/2026-07-31.md) — recorded during ADR writing