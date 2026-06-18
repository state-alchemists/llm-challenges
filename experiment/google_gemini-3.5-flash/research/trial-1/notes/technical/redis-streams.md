---
slug: redis-streams-pattern
---
# Redis Streams patterns for high-throughput asynchronous notifications

**Context:** Designing notification backbones on Redis Streams.
**Finding:** High-performance consumer group operations (`XGROUP`, `XREADGROUP`) provide cooperative scaling and reliable tracking. At-least-once delivery is managed via pending queues (`XPENDING`) and message claiming (`XCLAIM`). Memory usage is actively managed using stream trimming (`XTRIM` or `MAXLEN`).
**Source:** ADR-001-notification-architecture.md

## Backlinks
- [technical index](index.md) — technical index
- [2026-06-19 activity log](../activity-log/2026/2026-06/2026-06-19.md) — task completion log
