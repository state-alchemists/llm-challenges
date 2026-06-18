---
slug: notifier-subsystem-decision
---
# Notifier Subsystem Decision

**Context:** Selection of an asynchronous message broker for the Flask/PostgreSQL monolith.
**Finding:** Redis Streams is chosen over Apache Kafka for the notifications module due to extreme operational simplicity, under 2-week implementation time, sub-millisecond latencies for WebSockets, and cost compatibility.
**Source:** ADR-001-notification-architecture.md

## Backlinks
- [projects index](index.md) — project list
- [2026-06-19 activity log](../activity-log/2026/2026-06/2026-06-19.md) — task completion log
