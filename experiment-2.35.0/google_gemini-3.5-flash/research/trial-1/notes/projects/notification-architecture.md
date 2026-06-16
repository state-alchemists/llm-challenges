---
slug: notification-architecture-decoupling
---
# Notification Subsystem Architecture Decoupling

**Context:** Evaluated architectural decoupling of the SaaS project management notifications module under severe performance and operational constraints.
**Finding:** Selected Redis Streams over Apache Kafka because Redis is already in production, requires zero setup overhead, achieves 10x target throughput (~5,000 req/s), and offers native consumer groups for resilience. Exactly-once semantics for billing will be achieved using PostgreSQL-backed Transactional Outbox pattern and consumer-side unique constraint idempotency.
**Source:** ADR-001-notification-architecture.md

## Backlinks
- [Root Journal](../index.md) - listed recent insight
- [Projects Index](index.md) - listed project note
- [2026-06-15 log](../activity-log/2026/2026-06/2026-06-15.md) - architectural decision made on this day
