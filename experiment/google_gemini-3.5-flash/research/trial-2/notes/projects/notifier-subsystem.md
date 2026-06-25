---
slug: notifier-subsystem-redis-streams
---
# Selecting Redis Streams for Notification Subsystem

**Context:** When choosing a broker to decouple notifications synchronously processed in the monolith.
**Finding:** Redis Streams is selected over Apache Kafka due to our 6-person team size, 2-week time-to-value constraint, and existing production Redis setup. Throughput targets (5,000 req/s peak) are comfortably met, and exactly-once semantics for billing are handled via at-least-once Streams PEL retries combined with PostgreSQL application-level idempotency.
**Source:** ADR-001-notification-architecture.md

## Backlinks
- [HUD](../index.md) — referenced under Recent Insights
- [Projects Index](index.md) — project listing
- [2026-06-25 activity log](../activity-log/2026/2026-06/2026-06-25.md) — architectural decision drafted
