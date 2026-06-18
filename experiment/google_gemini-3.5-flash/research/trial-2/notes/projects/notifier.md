# Notifier Subsystem Project

We are evaluating and designing a decoupled notification system to replace synchronous notification processing in a Python/Flask SaaS platform.

## Key Facts & Decisions
- **Decision (2026-06-19)**: Selected Redis Streams over Apache Kafka as the main broker for asynchronous task notification delivery. Reuses existing Redis instance, avoids operational overhead, satisfies throughput (~25k msg/s peak at 10x scale) and latency requirements. See [ADR-001](../../../workdir/ADR-001-notification-architecture.md) for full details.
- **Idempotency Strategy**: Application-level deduplication via transaction/idempotency keys in PostgreSQL/Redis is required to achieve exactly-once processing (since workers deliver notifications to third-party SMTP and webhook APIs which can fail or timeout during network calls).
- **Durability Pattern**: Use the Transactional Outbox Pattern for billing-critical events.

## Backlinks
- [Projects Index](index.md)
- [2026-06-19 Log](../activity-log/2026/2026-06/2026-06-19.md)
