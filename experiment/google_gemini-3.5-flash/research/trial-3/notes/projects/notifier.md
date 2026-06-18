---
slug: notifier-architecture-decision
---
# Notifier Subsystem Architecture

**Context:** Decoupling the project management platform's synchronous notification loop.
**Finding:** We selected Redis Streams over Apache Kafka because of our tight 2-week timeline, small 6-person team with no Kafka/DevOps expertise, zero incremental infra cost, and natural integration with Redis Pub/Sub for WebSockets. Exactly-Once Semantics are handled via PostgreSQL database deduplication/idempotency keys.
**Source:** ADR-001-notification-architecture.md

## Backlinks
- [Root](../index.md)
- [Projects Index](index.md)
- [2026-06-19 log](../activity-log/2026/2026-06/2026-06-19.md) — drafted ADR comparing Kafka vs Redis Streams
