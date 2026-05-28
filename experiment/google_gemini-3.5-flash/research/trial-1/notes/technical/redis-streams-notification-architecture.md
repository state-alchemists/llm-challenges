---
slug: redis-streams-notification-architecture
---
# Redis Streams Notification Architecture

**Context:** Evaluating message broker options for asynchronous notification subsystem in a 6-person engineering team with strict budget, timeline (2 weeks), and operational constraints.
**Finding:** Redis Streams chosen over Apache Kafka due to minimal operational overhead, existing production footprint, native support for at-least-once delivery, consumer groups, and sufficient throughput capabilities (>50k ops/sec vs 5k ops/sec peak 10x target). Exactly-once delivery is implemented via at-least-once streaming and application-level consumer idempotency with a PostgreSQL deduplication table.
**Source:** system_context.md, ADR-001-notification-architecture.md

## Backlinks
- [activity-log/2026/2026-05/2026-05-28](activity-log/2026/2026-05/2026-05-28.md) — architectural decision recorded
