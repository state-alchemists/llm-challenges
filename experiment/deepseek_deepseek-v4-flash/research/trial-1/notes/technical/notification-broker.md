---
slug: notification-broker
---
# Notification broker decision — Redis Streams over Kafka

**Context:** SaaS PM platform, 6-person eng team (no infra engineer), no Kafka experience, ≤2-week setup constraint, Redis already in production, billing notifications need exactly-once.
**Finding:** Chose Redis Streams for the notification subsystem. Decisive factors: operational complexity (Kafka cluster burden vs. existing Redis ops), team size, timeline, budget. Key technical insight: neither broker provides end-to-end exactly-once for external side effects (email/webhook); exactly-once must come from consumer-side idempotency keys + unique constraint in Postgres, so Kafka's EOS doesn't tip the scale. Per-stream ordering + consumer groups with PEL/XACK satisfy at-least-once + retry; bound retention with MAXLEN.
**Source:** workdir/ADR-001-notification-architecture.md (verified against challenges/research/validator.py: EXCELLENT 1.0, 9/9 checks)

## Backlinks
- [2026-07-31 activity](activity-log/2026/2026-07/2026-07-31.md) — produced the ADR
