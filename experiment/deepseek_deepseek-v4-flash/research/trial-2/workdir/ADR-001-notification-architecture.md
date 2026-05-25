# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

---

## Context

The notification subsystem sends emails and webhooks when tasks are updated, assigned, or completed. It runs synchronously inside the HTTP request cycle of a Python/Flask monolith. As the platform has grown to 85,000 MAU and ~2M tasks/month, this design is breaking:

- **Request timeouts** — notifications add 800ms average latency, spiking to 8s.
- **Silent failures** — a downed email provider or webhook endpoint drops the notification with no retry or dead-letter queue.
- **Cascading failures** — slow webhook endpoints have caused database connection pool exhaustion twice this year, knocking out unrelated features.
- **No delivery guarantees** — billing-critical notifications ("trial expired", "payment failed") need exactly-once delivery but have no mechanism for it.

We need an asynchronous, decoupled architecture that supports retry with exponential backoff, at-least-once delivery for general notifications, exactly-once for billing events, and real-time WebSocket push within two quarters. The solution must handle 10x traffic growth without re-architecting.

**Constraints:**
- Engineering team of 6 (3 senior, 3 mid-level), no dedicated infrastructure engineer
- Redis already in production (session storage, rate limiting)
- Zero Kafka experience on the team
- Must deliver value within 2 weeks of starting work
- Modest budget — cannot afford managed Confluent Cloud at full scale
- Exactly-once semantics required for billing notifications

---

## Decision

**Use Redis Streams** as the backbone of the notification subsystem.

We will introduce a lightweight consumer-worker pattern on top of the existing Redis instance:

1. The Flask app writes notification events to a Redis stream (`notifications:events`) using `XADD`.
2. A set of Python worker processes (backed by consumer groups via `XREADGROUP`) consume events, send emails/webhooks, and acknowledge them with `XACK`.
3. Failed deliveries go to a dedicated dead-letter stream (`notifications:dlq`) after N retries with exponential backoff.
4. Billing events tag their stream entries with a deduplication key; consumers enforce idempotency at the application layer (check `XCLAIM` history + database write guard).
5. The same stream feeds real-time WebSocket push (planned Q2) by adding additional consumer groups that fan out to connected clients.

---

## Consequences

### Pros

- **Zero new infrastructure.** Redis is already deployed, monitored, and backed up. We add no new stateful system to the stack, no new daemon to tune, no new failure mode to learn. For a 6-person team with no infra engineer, this is the single strongest argument.
- **Familiar to the team.** Every developer already uses Redis for sessions and rate limiting. The Streams API (`XADD`, `XREADGROUP`, `XACK`, `XPENDING`) is well-documented and has mature Python client support (`redis-py`). Learning curve is days, not weeks.
- **Deliverable in <2 weeks.** The proven infrastructure means week 1 can focus on the worker loop and dead-letter logic, week 2 on integration and deployment. No cluster provisioning, no new CI pipelines, no Zookeeper/KRaft to configure.
- **Good enough throughput.** Redis Streams handles tens of thousands of messages per second on modest hardware. At peak 500 req/s, even at 10x growth (5,000 req/s) with ~2 notification events per request (10k msg/s), Redis comfortably meets the need. Kafka's millions/s throughput is unnecessary here.
- **Consumer groups built in.** Redis Streams supports `XREADGROUP` for work-queue semantics across multiple worker instances, `XPENDING` for monitoring stalled consumers, and `XCLAIM` for re-assigning failed messages — exactly the primitives needed for retry and at-least-once delivery.
- **Exactly-once is achievable at the application layer.** Redis Streams does not offer true exactly-once semantics at the broker level, but for the billing-critical subset of events, we achieve it via: (a) a deterministic deduplication key in the stream entry, (b) an idempotency guard in the database (e.g., `INSERT ... ON CONFLICT DO NOTHING`), and (c) periodic `XPENDING` reconciliation. This pattern is well understood and auditably correct for the volume involved (billing events are a small fraction of total traffic).
- **Natural path to WebSocket push.** Consumer groups in Redis Streams fan out cleanly — a second consumer group reads the same stream and pushes to WebSocket connections via Redis Pub/Sub, reusing the same infrastructure without cross-system data movement.
- **Modest budget.** The existing Redis instance has headroom; we scale vertically (larger instance type) or add a Redis replica well before hitting any ceiling. No per-partition pricing, no managed-streaming license.

### Cons

- **No true broker-level exactly-once.** Unlike Kafka's transactional API, Redis Streams requires application-layer idempotency for exactly-once guarantees. This is well-understood tech debt, but it means the billing path needs careful implementation and auditing.
- **Memory-bound retention.** Redis stores streams in memory. At 10x growth, long-term retention of all notification events for replay would be expensive. We will set a bounded retention via `MAXLEN` (~7 days of hot data) and archive archival records to S3/Cold storage separately. Full event replay is not a requirement today.
- **No log compaction.** Kafka's log compaction keeps the latest value per key — useful for state restoration. Redis Streams does not support this. For our use case (event-driven notifications, not state reconstruction), this is not a blocker.
- **Smaller ecosystem.** Kafka has Schema Registry, Kafka Connect, KSQL, and a rich connector ecosystem. Redis Streams integrates primarily through client libraries and Pub/Sub. For a 6-person team, the richer ecosystem also means more surface area to learn — this "con" may actually be a "pro" in disguise.
- **Consumer rebalancing is primitive.** When a consumer joins or leaves a Redis consumer group, `XREADGROUP` distributes entries across consumers with no explicit partition assignment. This works well for notification events (order-insensitive, small payloads) but means Redis Streams is unsuitable for workloads requiring strict per-key ordering across consumer changes.

---

## Alternatives Considered

### Apache Kafka (Rejected)

**Why it was considered:** Kafka is the industry standard for event streaming. It offers true exactly-once semantics via the transactional API, log compaction, multi-year retention on disk, and proven throughput in the millions of messages per second.

**Why it was rejected:**

1. **Operational cost exceeds team capacity.** A production Kafka cluster requires careful tuning of `num.partitions`, `replication.factor`, `min.insync.replicas`, broker heap sizing, page cache management, and partition rebalancing policies. For a 6-person team with no Kafka experience and no dedicated infrastructure engineer, this is a material risk. Self-hosting Kafka reliably is a full-time job. Confluent Cloud was evaluated but rejected on budget grounds at the projected 10x volume.

2. **Delayed time-to-value.** Standing up Kafka, learning the client APIs, integrating Schema Registry, and building CI/CD for topic management would exceed the 2-week window. Redis Streams can be delivering value in half the time.

3. **Over-engineered for the workload.** Kafka is designed for problems Redis Streams cannot solve: multi-year retention of high-volume event streams, log compaction for state reconstruction, and exactly-once stream processing across heterogeneous systems. Our problem is a notification queue with retry — a stream is the right primitive, but Kafka's superpowers come with weight we do not need. Peak throughput of 500 req/s (5,000 at 10x) is well below the threshold where Redis Streams becomes a bottleneck.

4. **Infrastructure surface area.** Adding Kafka means adding brokers, monitoring (JMX metrics, lag tracking), alerting, and on-call procedures for a completely new category of failure. The team already knows how to handle a Redis failure. A Kafka failure (e.g., partition leader election storm, unclean leader election, `UnderReplicatedPartitions`) is a new class of incident.

**When Kafka would be the right choice:** If we needed multi-year event retention with replay, exactly-once stream processing across multiple downstream systems (streams → database → analytics), or sustained throughput above 50,000 msg/s, Kafka would win. For a notification queue serving a 6-person startup, it is the wrong tool.

### PostgreSQL Queue via `SKIP LOCKED` (Rejected)

**Why it was considered:** Avoids any new infrastructure — the existing PostgreSQL instance can act as a queue. Polling with `SELECT ... FOR UPDATE SKIP LOCKED` is a well-documented pattern for work queues.

**Why it was rejected:**

1. **Database load.** Notification events at 10x volume (~10k writes/second) would add significant write pressure and table bloat (VACUUM overhead) to the primary database. Polling workers would add read pressure. The database is already the system's most contended resource.

2. **No native consumer group protocol.** PostgreSQL has no `XREADGROUP` equivalent. Each worker must independently poll, compare against its own claimed work, and handle rebalancing via application code. This is more code to write, test, and maintain than the Redis Streams equivalent.

3. **No built-in retry/DLQ semantics.** Dead-letter queues and retry with backoff would require additional tables and scheduled jobs. Redis Streams handles this with `XPENDING`/`XCLAIM` out of the box.

4. **Exactly-once is harder with row-level contention.** Idempotency guarantees require `SAVEPOINT` or transactional logic that increases lock contention. The Redis Streams approach with a deduplication key is simpler and doesn't compete with business-logic transactions for database resources.

5. **Redis is already in the stack.** Adding a queue-like workload to an overloaded PostgreSQL primary is strictly worse than using a Redis instance that is already provisioned and currently underutilized.

---

## Summary

| Criteria | Redis Streams | Apache Kafka | PostgreSQL Queue |
|---|---|---|---|
| New infrastructure | None | Zookeeper/KRaft cluster | None |
| Time to value | ~1 week | ~4+ weeks | ~2 weeks |
| Exactly-once | App-layer (acceptable) | Broker-native | App-layer (contended) |
| 10x throughput headroom | Yes | Yes | Marginal |
| Team experience | High (existing Redis) | None | High |
| Operational risk | Low | High | Medium |
| WebSocket path | Native (Pub/Sub) | Kafka → bridge | Requires polling |
| Budget impact | ~$0 (existing Redis) | $500+/mo (Confluent) or heavy ops | ~$0 |

Redis Streams is the correct choice for the team's size, the workload's scale, and the operational constraints. The exactly-once requirement for billing is achievable with well-understood application-layer idempotency that matches the event volume. As the platform grows, the worker layer can be scaled independently, and the stream can be migrated to a larger Redis instance or cluster without changing the consumer API.
