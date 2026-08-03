# ADR-001: Notification Subsystem Message Broker

## Status

Proposed

## Context

Our Python/Flask monolith (85k MAU, ~2M tasks/month, 500 req/s peak) handles notifications synchronously inside the HTTP request cycle. This has caused request timeouts (avg 800ms, spikes to 8s), silent failures with no retry, cascading failures from slow webhook endpoints, and no delivery guarantees for billing-critical notifications.

We need to decouple notification processing, support retry with exponential backoff, guarantee at-least-once delivery (exactly-once for billing events), and scale to 10x traffic without re-architecting. We have 4 web servers on AWS, an existing Redis cluster (session storage + rate limiting), and a 6-person engineering team with no dedicated infrastructure engineer and no Kafka experience. Setup/migration must deliver value within 2 weeks. Budget is modest.

## Decision

**We will use Redis Streams as the message broker for the notification subsystem.**

## Justification

### Technical fit for requirements

| Requirement | Redis Streams | Apache Kafka |
|---|---|---|
| Throughput | ~500k–1M msg/s on commodity hardware | ~1M+ msg/s with proper tuning |
| Ordering | Per-consumer-group ordering (XREAD with block) | Partition-level ordering, global with single partition |
| Message retention | 64-bit position indices, configurable retention | Time/size-based retention, configurable |
| Consumer groups | XREADGROUP with explicit ACK, at-least-once built-in | Consumer groups with offset management, exactly-once via transactions |
| Exactly-once | XREADGROUP + XACK; idempotent consumers needed for true exactly-once | Exactly-once semantics via transactions + idempotent producers |
| Operational complexity | Low — runs on existing Redis infra | High — separate cluster, topic partitioning, replication config |

The **scale target is 10x current traffic (~5,000 req/s peak)**. Redis Streams comfortably handles this on the existing Redis infrastructure without new servers. Kafka at this scale requires careful partition sizing, replication factor decisions, and JVM tuning — complexity that exceeds what a 6-person team without a dedicated infrastructure engineer can responsibly own.

**Exactly-once for billing notifications** is achievable with both: Redis Streams via `XREADGROUP` + `XACK` with idempotent consumers (store processed message IDs in a Redis set), Kafka via exactly-once transactions with idempotent producers. Both require application-level idempotency regardless. The difference is Kafka bundles this into its transaction API while Redis requires you to build it. Given our team already knows Redis, building a simple idempotency layer is straightforward.

**The 2-week constraint is decisive.** Redis Streams is an extension of the Redis API our team already uses. There is no new infrastructure to provision, no JVM to tune, no partition count to calculate. The migration path is: add a Redis Streams consumer as a sidecar process, migrate notification endpoints to publish to the stream instead of calling the mailer directly, then wire in retry/DLQ logic. Kafka requires: cluster provisioning (self-managed or partial managed), topic design, producer/consumer SDK integration, offset management understanding, and operational runbooks — typically 2–4 weeks for a team with no prior experience.

**Operational continuity** matters: we already have Redis expertise, Redis uptime SLAs, and Redis monitoring in place. Adding Streams is incremental. Kafka would introduce a second message broker requiring separate oncall coverage, separate monitoring, and a new failure domain.

## Consequences

### Pros of Redis Streams

1. **No new infrastructure** — reuses existing Redis cluster; no additional operational surface area.
2. **Familiar API** — team writes Redis commands already; Streams commands (`XADD`, `XREADGROUP`, `XACK`, `XRANGE`) are a natural extension.
3. **Fast migration** — existing code publishes to a stream; a separate consumer process reads, dispatches, and ACKs. Rollback is a config change.
4. **Built-in consumer groups** — `XREADGROUP` provides at-least-once with ACK, matching our retry requirement.
5. **Leverages existing Redis investment** — monitoring, backup, and failover are already in place.
6. **Scales to 10x** — 500k–1M msg/s throughput exceeds our 5,000 req/s target by 2 orders of magnitude.
7. **Stream length awareness** — `XLEN` and `XRANGE` make it trivial to inspect queue depth; `XTRIM` enforces retention limits.

### Cons of Redis Streams

1. **No native exactly-once** — requires application-level idempotency (store processed message IDs in a Redis set). This is straightforward but adds code.
2. **Single-node head-of-line blocking** — if a slow consumer stalls, Redis Streams does not auto-rebalance the consumer group the way Kafka does with partition rebalancing. Requires manual `XGROUP SETID` or consumer restart.
3. **No native backpressure propagation to producers** — Redis Streams will accept messages faster than slow consumers can process them; queue depth grows until `MAXLEN` is hit. Mitigation: monitor `XLEN`, alert on growth, scale consumers horizontally.
4. **Ecosystem tooling** — Kafka has richer ecosystem (schema registry, Kafka Connect, ksqlDB). Redis Streams is sufficient but less batteries-included.
5. **Message replay is range-based** — `XRANGE` by stream position works but is less ergonomic than Kafka's offset-based replay.

### Mitigations for identified cons

- **Exactly-once**: Implement idempotent consumers by storing `XMessageID` in a Redis set with TTL; check membership before processing. One Redis SET operation per message.
- **Consumer group rebalancing**: Use `XREADGROUP BLOCK` with a reasonable `BLOCK` timeout (1–5s). If a consumer dies, its pending messages (`XPENDING`) are visible and can be reassigned. Manual intervention is rare in practice.
- **Backpressure**: Set `MAXLEN` or `MAXLEN~` on `XADD` to cap stream length. Monitor `XLEN` via existing Redis monitoring. Scale consumer goroutines/workers horizontally when queue grows.

## Alternatives Considered

### Apache Kafka

**Why rejected:**

1. **Operational overhead exceeds team capacity.** Kafka requires managing brokers, ZooKeeper or KRaft, replication factor, partition count, consumer group lag monitoring, and JVM tuning. With no dedicated infrastructure engineer, this creates an operational burden disproportionate to the problem scale.

2. **Steep learning curve on the 2-week timeline.** The team has zero Kafka experience. Producing a working, operationally sound Kafka integration in 2 weeks requires cut corners — likely no proper error handling, no DLQ strategy, no monitoring — that would technical debt the system.

3. **Infrastructure cost.** Self-managed Kafka on 4+ EC2 instances (for replication and ZooKeeper) exceeds our modest budget. Managed Confluent Cloud at sufficient scale is not affordable at full 10x load.

4. **Over-engineering for our scale.** At 5,000 req/s peak with 10x growth target, Kafka is the right tool for tens of thousands of req/s with multiple downstream consumers, complex stream processing, or cross-dc replication. Our use case — fire-and-forget notifications with one consumer group and retry logic — does not justify the complexity.

5. **New failure domain.** Adding Kafka introduces a second critical path that can fail independently of Redis. Two message brokers mean twice the oncall surface and twice the failure modes.

**Kafka would be the correct choice if:**
- We had a dedicated platform/infrastructure team
- We needed multi-consumer fan-out (different consumers for email, SMS, webhook, analytics)
- We were building event-sourcing or audit-log infrastructure
- Scale was an order of magnitude higher (50k+ req/s)

Given our constraints, Kafka's capabilities exceed our requirements, and its operational complexity exceeds our team's capacity to manage it safely.

---

*ADR authored for system_context.md requirements. Review after 90 days or upon significant traffic change.*
