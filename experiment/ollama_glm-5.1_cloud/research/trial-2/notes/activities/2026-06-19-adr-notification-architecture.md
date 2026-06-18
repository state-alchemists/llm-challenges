# Activity: Wrote ADR-001 for Notification Subsystem

- **Date**: 2026-06-19
- **Artifact**: `ADR-001-notification-architecture.md` in workdir

## Summary

Authored an Architecture Decision Record evaluating Apache Kafka vs Redis Streams for the notification subsystem of a SaaS project management platform.

**Decision: Redis Streams** — justified by:
- 6-person team, no infra engineer, no Kafka experience
- 2-week delivery window
- Already running Redis in production
- Throughput requirements (1,500 msgs/s current, 15K msgs/s at 10× growth) well within Redis Streams' capacity
- Exactly-once for billing requires application-level idempotency regardless of transport
- Redis Pub/Sub + Streams is a natural fit for upcoming WebSocket push

Key trade-offs documented: memory-bounded retention (mitigated by PostgreSQL as durable source of truth), no native exactly-once, single-node risk (mitigated by primary-replica failover), future Kafka migration cost is bounded and acceptable.