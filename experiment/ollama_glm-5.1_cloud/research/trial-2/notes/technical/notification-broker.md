# Notification Broker: Redis Streams vs Kafka

**Decision**: Redis Streams for the notification subsystem.

**Key insight**: "Exactly-once" in practice requires application-level idempotency on *both* Kafka and Redis Streams — consumer crashes before offset/ACK commit cause redelivery regardless of broker. A PostgreSQL idempotency key table (`INSERT ... ON CONFLICT DO NOTHING`) closes this gap uniformly, making Redis Streams' lack of native EOS less of a disadvantage than it appears.

**Constraints that drove the choice**: 6-person team with no Kafka experience, no dedicated infra engineer, 2-week time-to-value deadline, Redis already in production, modest budget, throughput well within single-instance Redis capacity (~500 req/s peak, 10× target = 5,000 req/s).

**When to reconsider**: If sustained throughput exceeds ~50,000 msgs/s, or if the team grows to include dedicated infra engineers and needs multi-service event sourcing.

## Backlinks

- [2026-06-16 log](../activity-log/2026/2026-06/2026-06-16.md) — ADR-001 written this day
- [llm-challenges project](../projects/llm-challenges.md) — challenge workdir where system_context.md lives
- [technical index](index.md) — listed under technical notes
- [root index](../index.md) — listed under recent insights