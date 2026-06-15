# Redis Streams vs Apache Kafka for Notification Subsystems

## Finding

For a small team (≤6 engineers, no dedicated infra) building an async notification pipeline at moderate scale (≤5K req/s peak), Redis Streams is the better choice despite Kafka's superior exactly-once transactions and durable log retention. The decisive factors are:

1. **Operational simplicity**: Redis Streams reuses existing Redis infrastructure and team knowledge. Kafka requires standing up a new cluster (ZooKeeper/KRaft, brokers, monitoring).
2. **Time to value**: Redis Streams consumer groups (`XREADGROUP`, `XACK`, `XPENDING`, `XCLAIM`) provide at-least-once delivery, retry, and dead-letter handling out of the box — no new cluster needed.
3. **Exactly-once for billing**: Achieved via application-level deduplication (PostgreSQL unique constraint on notification ID + event type), not broker-level transactions. This is sufficient when the exactly-once subset (billing) is small relative to total notification volume.

**Kafka wins when**: throughput exceeds ~100K msgs/s, multi-day event replay is required, or the team has dedicated Kafka expertise and operational capacity.

## Backlinks
- [technical index](index.md) — listed under Technical Notes
- [root index](../index.md) — listed under Recent Insights
- [2026-06-15 activity log](../activity-log/2026/2026-06/2026-06-15.md) — ADR written this date