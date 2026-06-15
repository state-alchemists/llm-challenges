---
slug: redis-streams-over-kafka
---
# Redis Streams Over Kafka for Notification Subsystem

**Context:** Choosing a message broker for a SaaS project management platform's notification subsystem (6-person team, Redis already in production, no Kafka experience, 2-week delivery deadline).

**Finding:** Redis Streams is the correct choice over Apache Kafka. The deciding factors are: (1) team already operates Redis vs. zero Kafka experience, (2) 2-week delivery constraint makes Kafka infeasible, (3) Kafka's exactly-once semantics do not eliminate the need for application-level idempotency at external consumers (email/webhook), (4) current and 10x projected scale (~5K req/s) is well within Redis Streams capability, (5) budget rules out managed Confluent Cloud. Kafka would be revisited only if volume exceeds 50K msgs/s or multi-team event streaming with replay is needed.

**Source:** system_context.md, ADR-001-notification-architecture.md

## Backlinks
- [2026-05-30 activity log](../activity-log/2026/2026-05/2026-05-30.md) — when this decision was recorded