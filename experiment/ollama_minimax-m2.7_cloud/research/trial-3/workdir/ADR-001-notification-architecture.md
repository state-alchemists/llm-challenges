# ADR-001: Notification Subsystem Message Broker

**Status:** Proposed

---

## Context

The notification module currently executes synchronously inside the HTTP request cycle. This has caused request timeouts (avg 800ms, spikes to 8s), silent dropped notifications, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical events.

We need to migrate to an asynchronous message broker to decouple notification dispatch from the request cycle, support retry with exponential backoff, guarantee at-least-once (and for billing events, exactly-once) delivery, and handle 10x traffic growth.

**Non-negotiable constraints:**
- 6-person engineering team, no dedicated infrastructure engineer, no Kafka experience
- Must deliver value within 2 weeks of starting work
- Cannot afford managed Confluent Cloud at scale
- Must maintain exactly-once semantics for billing notifications
- Redis is already in production (session storage, rate limiting)

**Workload profile:**
- Peak: ~500 HTTP req/s
- Notification fanout: 1–3 messages per request (email, webhook, in-app push)
- Burst traffic during business hours, predictable patterns
- Billing events are a small subset (~5%) but have strict delivery requirements

---

## Decision

**Chosen option: Redis Streams**

Redis Streams is the correct choice given the team's size, constraints, and operational context. It satisfies every hard requirement with the infrastructure we already run, at a fraction of the complexity and cost of Apache Kafka.

### Technical justification

**Throughput:** At peak we generate an estimated 500–1,500 notification messages per second (worst case: 3 messages × 500 req/s). Redis Streams sustains 50,000–100,000+ operations per second on a modern instance — a 30–100x safety margin over our 2-year scaling target. Kafka has higher theoretical throughput, but that ceiling is irrelevant when we are not approaching it.

**Ordering guarantees:** Redis Streams guarantees intra-stream ordering by insertion order (XADD assigns a monotonic ID). Consumer groups (XREADGROUP) preserve this ordering per consumer. Kafka also provides strong ordering within a partition, but Redis achieves this without requiring partition count planning or re-keying strategies.

**Exactly-once delivery:**
- Redis Streams via consumer groups delivers **at-least-once** semantics natively. Messages are not removed from the stream on read — they are acknowledged explicitly with XACK.
- **Exactly-once** for billing notifications is achieved by making the handler idempotent: write a deduplication key (e.g., `notification:idempotency:{event_id}`) to Redis before processing, with a TTL longer than the retry window. If the handler crashes after side effects (email sent) but before XACK, replay will detect the already-processed event and skip re-execution.
- Kafka's exactly-once semantics (transactions) require explicit producer configuration and adds non-trivial complexity. The idempotent handler pattern on Redis Streams achieves equivalent guarantees with less operational surface.

**Message retention:** Redis Streams supports configurable MAXLEN (or MAXLEN~ for approximate trimming). Retention can be set to match the maximum retry window (e.g., 7 days), and a dead-letter stream (separate stream) captures failed messages after max retries.

**Consumer groups:** XREADGROUP supports multiple concurrent consumers in a consumer group with load balancing. This allows horizontal scaling of worker processes without code changes. Pending entries (unacknowledged messages) are automatically redistributed after a configurable idle timeout (XPENDING), providing crash recovery without manual intervention.

**Operational complexity:** Redis Streams is a data structure in the Redis process already running on your infrastructure. No new servers, no JVM tuning, no partition rebalancing, no Kafka expertise required. The team writes to a stream and reads from it using existing Redis client libraries (e.g., `redis-py`). Operational knowledge transfers directly.

---

## Consequences

### Pros of Redis Streams

1. **No new infrastructure.** Extends the existing Redis deployment already running in production for sessions and rate limiting. No new servers, no new managed services.
2. **Two-week delivery is achievable.** The API surface is small (XADD, XREADGROUP, XACK, XPENDING). A working prototype with retry and dead-letter handling can be running in days.
3. **Familiar operational tooling.** Monitoring (INFO, MONITOR), persistence (RDB + AOF), and failover behavior are already understood by the team.
4. **Horizontal worker scaling.** Consumer groups allow adding worker processes without code changes. Each worker claims messages atomically.
5. **Built-in pending entry redistribution.** If a worker crashes, unacknowledged messages become visible to other workers after the idle timeout — no manual intervention required.
6. **Cost.** Self-hosted on existing infrastructure. No additional spend.
7. **Future WebSocket push.** The same Redis instance can serve pub/sub channels for real-time push notifications planned within 2 quarters, requiring no additional infrastructure.

### Cons of Redis Streams

1. **Not a distributed log in the Kafka sense.** Redis Streams is a single-shard ordered log. If Redis itself becomes a bottleneck at very high throughput (beyond what this system will see in the 2-year planning horizon), horizontal scaling requires Redis Cluster configuration. Kafka is designed from the ground up for multi-broker distribution.
2. **No native compaction or log-segment pruning.** Kafka's log compaction retains the last known value per key indefinitely. Redis Streams MAXLEN trims old messages but does not compact by key. For audit-trail use cases this can matter.
3. **Ecosystem maturity.** Kafka has deep integrations with data pipelines, connectors, and stream processing frameworks (ksqlDB, Flink). Redis Streams does not. If the notification system evolves into a broader event-streaming platform, Kafka's ecosystem is richer.
4. **Operational visibility.** Kafka's metrics (consumer lag, replication status, ISR size) are more granular for capacity planning. Redis Streams monitoring requires more manual instrumentation.
5. **Large message support.** Kafka handles multi-MB messages comfortably. Redis Streams is optimized for small to medium payloads; large messages impact memory and should be avoided.

---

## Alternatives Considered

### Apache Kafka

Kafka was evaluated but rejected for the following reasons:

**Team experience:** No Kafka experience on the team today. The operational model — brokers, topics, partitions, consumer groups, offset management, replication factor, ISR tuning — requires non-trivial learning investment. With a 6-person team and a 2-week delivery constraint, this learning curve is prohibitive.

**Infrastructure overhead:** Self-hosted Kafka requires a minimum of 3 brokers for proper replication, plus ZooKeeper (or KRaft in newer versions). JVM tuning, disk I/O configuration, and partition leadership balancing are operational concerns that need an infrastructure engineer. We have none.

**Managed Kafka (Confluent Cloud / MSK):** Confluent Cloud at the throughput and retention levels required exceeds our current budget. Amazon MSK reduces operational burden but still requires cluster sizing expertise and carries significant cost at scale.

**Over-engineering for current scale:** Kafka's sweet spot is millions of messages per second across dozens of consumers with complex stream processing needs. Our current throughput is ~1,500 msg/s at peak, growing to an estimated 15,000 msg/s at 10x scale — still within Redis Streams' comfortable range. Kafka's capabilities outpace our requirements by a wide margin, creating unnecessary complexity.

**Exactly-once complexity:** Kafka's exactly-once semantics (EOS) requires producer transactions, idempotent producers, and careful consumer commit strategies. While more theoretically robust than Redis Streams' idempotent-handler pattern, the implementation complexity is substantially higher.

**Kafka is not eliminated for the future.** If the platform evolves to require multi-datacenter replication, complex event stream processing, or the notification system becomes a gateway to a broader event-driven architecture, Kafka should be re-evaluated. Today it is the wrong tool for this team at this stage.

---

## Summary

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| Team familiarity | High (already in production) | None |
| New infrastructure required | None | 3+ brokers + ZooKeeper/KRaft |
| 2-week delivery | Achievable | High risk |
| Peak throughput (1,500 msg/s) | Comfortably supported | Overkill |
| 10x scale (15,000 msg/s) | Supported | Overkill |
| Ordering guarantees | Per-stream, guaranteed | Per-partition, guaranteed |
| Exactly-once (billing) | Idempotent handler (achievable) | Kafka transactions (more complex) |
| Consumer group support | Yes (XREADGROUP) | Yes |
| Retry / DLQ | Stream + MAXLEN + separate DLQ stream | Dead letter topic pattern |
| Operational complexity | Low | High |
| Monthly cost | $0 (self-hosted) | $500–$5,000+ (managed) |

**Recommendation:** Adopt Redis Streams for the notification subsystem. Implement billing notifications with an idempotent handler pattern using Redis deduplication keys. Use a separate dead-letter stream for messages that exceed the retry threshold. Monitor consumer lag via XPENDING and stream length. This delivers a correct, operationally simple, and cost-effective solution within the 2-week constraint.