# ADR-001: Notification Subsystem Message Broker

## Status

**Proposed**

## Context

The notification module currently executes synchronously inside the HTTP request cycle, causing request timeouts (avg 800ms, spikes to 8s), silent failures with no retry, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical notifications.

**Requirements:**
- Decouple notifications from HTTP request cycle (async processing)
- Retry with exponential backoff
- At-least-once delivery for billing events; exactly-once where feasible
- Support real-time WebSocket push within 2 quarters
- Handle 10x traffic growth (500 req/s → 5,000 req/s peak)

**Constraints:**
- 6-person engineering team (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already in production (session storage, rate limiting)
- No Kafka experience on the team
- Maximum 2-week setup/migration before delivering value
- Modest budget; cannot afford managed Confluent Cloud
- Exactly-once semantics required for billing notifications

## Decision

**Choose Redis Streams** as the message broker for the notification subsystem.

### Justification

Given the team's size, constraints, and existing Redis footprint, Redis Streams provides the best balance of capability, operational simplicity, and time-to-value.

**Scale fit:** At 500 req/s peak (targeting 5,000 req/s), Redis Streams comfortably handles 500k–1M events/second on a single instance. This provides an order-of-magnitude safety margin without requiring cluster sharding or partition management.

**Operational continuity:** The team already operates Redis in production. Adding Streams requires no new infrastructure, no new operational knowledge beyond Redis documentation, and no on-call rotation changes. Kafka would require the team to learn ZooKeeper/KRaft, partition assignment, replication factor tuning, leader election, and consumer group rebalancing—none of which are trivial with no dedicated infra engineer.

**Time-to-value:** Redis Streams can be adopted incrementally. The Flask app publishes to a stream, a single worker process consumes it—functional within days. Kafka's cluster provisioning, topic configuration, and producer/consumer implementation typically requires 2–4 weeks for a team with no prior experience.

**Exactly-once for billing:** Redis Streams consumer groups with `XREADGROUP` + manual `XACK` + idempotent message processing (deduplication via unique message IDs) achieves exactly-once semantics at the application layer. This is well-understood and straightforward to implement. Kafka's transactional API provides exactly-once out of the box but adds significant operational complexity.

## Consequences

### Benefits

- **Operational simplicity:** Redis is already on-call; no new systems to monitor
- **Low learning curve:** Team can reference existing Redis knowledge; Streams documentation is minimal
- **Sufficient throughput:** 500k–1M events/sec capacity vs. 5,000 req/s needed (100x headroom)
- **Consumer groups:** Native support since Redis 5.0; enables multiple workers, competing consumers, and load balancing
- **Message acknowledgment:** `XACK` + pending entry list (PEL) provides at-least-once delivery with retry
- **Dead-letter handling:** `XPENDING` + `XCLAIM` allows redelivery of unacknowledged messages after timeout
- **Retention:** Configurable via `MAXLEN` or `MINID`; can retain messages for replay or debugging
- **Ordering:** Per-stream total ordering simplifies debugging and ensures notification sequence
- **WebSocket readiness:** Redis pub/sub (`PUBLISH`/`SUBSCRIBE`) can fan out to WebSocket servers for real-time push; can coexist with Streams in the same Redis instance
- **Cost:** No additional infrastructure cost; self-managed on existing Redis instance

### Drawbacks

- **No native exactly-once:** Requires application-level deduplication (store processed message IDs in a Redis SET or PostgreSQL table). Kafka offers transactional exactly-once out of the box.
- **Single-instance bottleneck:** A single Redis instance is the bottleneck. At extreme scale (>100k req/s), would need Redis Cluster, which introduces operational complexity. However, this threshold is 20x above current projections.
- **No log compaction:** Kafka supports log compaction for key-based events; Redis Streams does not. If notification state needs to be reconstructed, Kafka is superior.
- **Monitoring maturity:** Redis Streams monitoring (via `XINFO`) is less mature than Kafka's offset lag metrics and consumer group monitoring.
- **Replication:** Redis replication is asynchronous; a Redis failover could lose the last few messages if not using Redis Cluster with quorum writes. Acceptable for notifications; critical for billing would require additional safeguards.

## Alternatives Considered

### Apache Kafka

Kafka offers superior throughput (millions of events/sec), true exactly-once semantics via the transactions API, log compaction, and mature ecosystem tooling (Kafka Connect, Schema Registry). However, it was rejected for the following reasons:

| Factor | Kafka | Redis Streams |
|--------|-------|---------------|
| Team experience | None | Existing production use |
| Setup time | 2–4 weeks | 1–3 days |
| Operational overhead | High (cluster management, partition rebalancing) | Low (same Redis instance) |
| Exactly-once | Native (transactions API) | Application-level deduplication |
| Throughput needed | 5,000 req/s | 5,000 req/s |
| Kafka capacity | Massive overprovision | Well within single-instance limits |
| Infrastructure cost | New cluster (EC2 instances or MSK) | Zero (existing Redis) |

Kafka's strengths—massive throughput, log compaction, and native exactly-once—are not relevant at the current or projected scale. Its weaknesses—operational complexity, learning curve, and 2-week minimum setup—are directly at odds with the project constraints. If the team were larger, had a dedicated platform engineer, or projected 10x higher throughput, Kafka would be the clear choice.

---

## Recommendation

**Adopt Redis Streams now.** Implement idempotent notification processing by storing processed message IDs in a dedicated Redis SET (with TTL). This achieves exactly-once semantics for billing notifications without Kafka's operational burden.

**Migration sequence:**
1. Add Redis Streams producer to Flask (publish notification events, don't send directly)
2. Deploy a single worker process consuming via `XREADGROUP`
3. Implement exponential backoff retry with dead-letter tracking
4. Add idempotency deduplication for billing event types
5. (Future) Add WebSocket fan-out using Redis pub/sub

If, within 6–12 months, throughput exceeds 50,000 req/s or the team grows a dedicated infrastructure engineer, revisit Kafka as a future migration target.