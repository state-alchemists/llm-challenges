# ADR-001: Redis Streams for Notification Subsystem

**Decision:** Redis Streams over Apache Kafka for the async notification broker.

**Context:** 85k MAU SaaS platform, 500 req/s peak, synchronous notifications causing timeouts and cascading failures. 6-person team, no Kafka experience, Redis already in production.

**Key factors:**
- Zero new infrastructure — Redis already running for session/rate limiting
- Team already knows `redis-py` — first worker in days, not weeks
- Consumer groups with `XAUTOCLAIM` for retry/DLQ — well-documented pattern (Redis official tutorial)
- Exactly-once for billing via idempotency keys in PostgreSQL — Kafka's native exactly-once wouldn't help for external HTTP/SMTP side effects anyway
- WebSocket push via Redis Pub/Sub on the same stack
- ~1,500 ev/s current, ~15,000 at 10x — well within Redis Streams throughput

**Rejected:** Apache Kafka — operational complexity, team learning curve, cost ($430+/month MSK), overkill for current scale

**File:** `ADR-001-notification-architecture.md` in workdir

## Backlinks
- [2026-06-25 activity log](../activity-log/2026/2026-06/2026-06-25.md) — ADR written here
