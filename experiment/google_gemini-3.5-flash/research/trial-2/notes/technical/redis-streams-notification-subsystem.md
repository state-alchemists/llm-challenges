---
slug: redis-streams-notification-subsystem
---
# SaaS Notification Subsystem Choice: Redis Streams

**Context:** Decouple monolithic synchronous notifications with strict delivery, 10x scale, and exactly-once billing requirements under tight operational constraints.
**Finding:** Redis Streams is the optimal choice over Apache Kafka due to:
1. Operational overhead of Kafka cannot be supported by a 6-person team with zero Kafka experience.
2. Redis is already deployed and monitored in our production stack, satisfying the 2-week time-to-value constraint.
3. Scaling peak throughput of 5,000 req/s is well within Redis Streams capacity (>50k ops/s).
4. Native consumer groups (`XGROUP`, `XPENDING`, `XACK`) provide the guarantees needed for reliable notification retries.
5. Exactly-once semantics for billing events require application-level deduplication (e.g., PostgreSQL transaction locks) regardless of broker choice.
**Source:** ADR-001-notification-architecture.md
