---
slug: notification-architecture
---
# Notification Subsystem: Redis Streams over Kafka

**Context:** SaaS project management platform (85K MAU, 500 req/s peak) needs to decouple notifications from the HTTP request cycle; team of 6 with no Kafka ops experience, 2-week delivery deadline, modest budget, Redis already in production.

**Finding:** Redis Streams is the right choice for the notification message broker. Kafka's advantages (massive throughput beyond 5K req/s, long-term log retention, broker-level exactly-once transactions) are overkill for current and projected scale. Exactly-once for billing is achieved via idempotent consumers with a PostgreSQL idempotency table — the same pattern most Kafka deployments use in practice. The deciding factors are: (1) zero new infrastructure (Redis already running), (2) team already knows Redis ops, (3) 2-week timeline achievable, (4) budget allows no managed Kafka. Re-evaluate if sustained throughput exceeds 50K msg/s or a company-wide event backbone is needed.

**Source:** ADR-001-notification-architecture.md

## Backlinks
- [2026-06-19 activity](../activity-log/2026/2026-06/2026-06-19.md) — ADR written this session
- [journal index](../index.md) — listed under Recent Insights
- [technical index](index.md) — listed under technical notes