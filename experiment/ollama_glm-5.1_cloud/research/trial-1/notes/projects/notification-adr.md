# Notification ADR

Decision record for the notification subsystem architecture. Chose Redis Streams over Apache Kafka.

## Key Facts
- System: Python/Flask monolith, 85K MAU, 500 req/s peak
- Team: 6 engineers, no dedicated infra, no Kafka experience
- Constraint: 2-week setup window, modest budget
- Decision: Redis Streams with PostgreSQL outbox for exactly-once billing notifications

## Backlinks
- [2026-06-16 activity](../activity-log/2026/2026-06/2026-06-16.md) — ADR written on this date