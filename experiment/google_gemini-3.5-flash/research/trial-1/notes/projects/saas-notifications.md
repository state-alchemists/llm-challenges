---
slug: saas-notifications-architecture
---
# SaaS Project Management — Notifications Architecture

**Context:** Selection of technology for asynchronous notification subsystem.
**Finding:** Decided to use Redis Streams as the core message broker, integrated with application-level PostgreSQL transaction logging for exactly-once billing event guarantees. Apache Kafka was rejected due to operational complexity (6-person team, no dedicated DevOps), timeline constraints (< 2 weeks), and budget limits.
**Source:** ADR-001-notification-architecture.md

## Backlinks
- [projects index](index.md) — listed in project index
- [2026-07-29 activity log](../activity-log/2026/2026-07/2026-07-29.md) — decision finalized
