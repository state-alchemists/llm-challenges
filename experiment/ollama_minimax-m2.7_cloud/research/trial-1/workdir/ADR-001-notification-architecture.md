# ADR-001: Notification Subsystem Message Broker Selection

## Status

Proposed

## Context

### Problem Statement

The notification module (email + webhook) runs synchronously inside the HTTP request cycle, causing:
- Average latency of 800ms, spiking to 8s during peak hours (request timeouts)
- Silent notification drops when email providers or webhook endpoints are unavailable (no retry, no DLQ)
- Two cascading failure incidents where slow webhook endpoints exhausted connection pools
- No delivery guarantees for billing-critical notifications

### System Scale

| Metric | Value |
|--------|-------|
| Monthly Active Users | 85,000 |
| Tasks Created/Month | ~2,000,000 |
| Peak Request Rate | ~500 req/s |
| Current Redis Usage | Session storage, rate limiting |

### Constraints

- **Team**: 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure engineer
- **Kafka experience**: None on the team
- **Redis experience**: Already in production (session storage, rate limiting)
- **Timeline**: Must deliver value within 2 weeks of starting migration
- **Budget**: Modest; cannot afford managed Confluent Cloud at full scale
- **Delivery guarantee**: Exactly-once semantics required for billing notifications (trial expired, payment failed)

### Scaling Targets

- Decouple notifications from the HTTP request cycle (async processing)
- Retry with exponential backoff
- At-least-once delivery for general notifications; exactly-once for billing events
- WebSocket push notifications within 2 quarters
- Handle 10x traffic growth (5,000 req/s) without re-architecting

---

## Decision

**Chosen Option: Redis Streams**

Redis Streams is selected as the message broker for the notification subsystem, implemented as a producer-consumer pattern with consumer groups for fan-out to email and webhook processors.

### Justification

The decision prioritizes **team constraints and time-to-value** over theoretical maximum throughput:

1. **Operational familiarity**: The team already operates Redis in production. Adding Redis Streams leverages existing knowledge, monitoring tooling, and operational runbooks. No new infrastructure to deploy.

2. **Two-week delivery**: Redis Streams can be integrated incrementally. The Flask app produces to a stream; a single worker process consumes and dispatches. Kafka requires cluster provisioning, topic configuration, partitioning strategy, consumer group setup, and offset management—substantially more than two weeks before first value.

3. **Throughput adequacy**: At 500 req/s peak (targeting 5,000 req/s for 10x growth), Redis Streams comfortably handles the workload. Redis Streams sustains 100,000+ events/second on commodity hardware; Kafka's million-event ceiling is not yet relevant at this scale.

4. **Existing investment**: Redis is already a production dependency. No new managed service costs.

5. **Exactly-once via deduplication**: While Redis Streams provides at-least-once delivery, billing notifications can achieve exactly-once semantics by writing a deduplication key to Redis (or PostgreSQL) before processing. This is a well-understood pattern and aligns with the constraint.

---

## Consequences

### Benefits of Redis Streams

| Property | Behavior |
|----------|----------|
| **Ordering** | Per-consumer-group ordering is guaranteed (XREADGROUP) |
| **Consumer groups** | Native support via XREADGROUP; enables parallel processing and fan-out |
| **Message retention** | Configurable via `MAXLEN` or `MINID` trimming policies; up to 512GB per stream |
| **Throughput** | 100,000+ events/second; exceeds 10x growth target (5,000 req/s) |
| **Latency** | Sub-millisecond reads with XREADGROUP BLOCK |
| **Operational complexity** | Low; same Redis instance, no new service to operate |
| **At-least-once** | Native; messages are acknowledged only after successful processing |
| **Exactly-once (billing)** | Achievable via consumer-side deduplication (write dedup key before processing) |
| **Setup time** | 1–2 days for core integration; delivers value within the 2-week constraint |

### Drawbacks and Mitigations

| Drawback | Impact | Mitigation |
|----------|--------|------------|
| **No native dead-letter queue** | Failed messages after max retries need manual routing | Implement a DLQ stream (`notifications.dlq`) by routing exhausted messages explicitly in worker code |
| **Pending entries list (PEL) growth** | Unacknowledged messages accumulate in PEL; can grow large | Use `XREADGROUP` with `ENTRYID older-than` or periodic `XPENDING` cleanup; acknowledge after processing |
| **Memory-bound retention** | Stream trimming evicts oldest messages if `MAXLEN` is hit | Set `MAXLEN ~` with sufficient headroom; monitor `used_memory` |
| **Less ecosystem tooling** | No native schema registry, Kafka Connect, or stream processing | Not needed at current scale; can add later if stream processing is required |
| **Not designed for huge fan-out** | WebSocket push at scale may need a separate mechanism | Redis Pub/Sub or a dedicated WebSocket service can supplement; fits within the 2-quarter roadmap |
| **Exactly-once requires application logic** | Not native like Kafka Transactions | Deduplication table in PostgreSQL keyed on notification ID; check before processing |

### Comparison Summary

| Criterion | Redis Streams | Apache Kafka |
|-----------|---------------|--------------|
| Throughput (events/sec) | 100,000+ | Millions |
| Ordering guarantee | Per consumer group | Per partition |
| Message retention | Memory-bounded (configurable) | Disk-bounded, configurable |
| Consumer groups | Yes (XREADGROUP) | Yes (native) |
| Exactly-once semantics | Via application dedup | Native (transactions) |
| Operational complexity | Low | High |
| Setup/integration time | 1–2 weeks | 4–8 weeks |
| Team experience required | Low (existing Redis) | High (new technology) |
| Managed service cost | Low (existing Redis) | High (Confluent/RDKS) |

---

## Alternatives Considered

### Apache Kafka

**Why it was rejected:**

1. **Prohibitive learning curve**: No Kafka experience on the team. Operationalizing Kafka—cluster sizing, replication factor, acknowledgment configuration, consumer group rebalancing, topic partitioning strategy—requires expertise the team does not have. A dedicated infrastructure engineer is typically needed.

2. **Time-to-value mismatch**: Managed Kafka services (Confluent Cloud, AWS MSK) require weeks of configuration before delivering business value. Self-hosted Kafka is even more time-intensive. The two-week constraint explicitly prohibits this path.

3. **Over-engineering for current scale**: Kafka's design targets millions of events per second across dozens of consumers with complex stream processing. Our current load (500 req/s, targeting 5,000 req/s) is orders of magnitude below where Kafka's complexity pays off.

4. **Budget risk**: Managed Kafka at production scale (multi-AZ, monitored, backed up) exceeds modest budget constraints. Self-hosted Kafka requires dedicated infrastructure engineering time.

5. **No existing investment**: Kafka would be a new operational dependency. Redis Streams builds on what we already run.

**Kafka would be reconsidered if:**
- Scale exceeds 50,000 events/second sustained
- Complex stream processing (e.g., notification aggregation, event sourcing) is required
- A dedicated infrastructure engineer joins the team
- Budget allows for managed Confluent Cloud

---

## Appendix: Recommended Redis Streams Architecture

```
┌──────────────┐     ┌─────────────────────┐
│ Flask App    │────▶│ Stream: notifications│
│ (Producer)   │     │ • type: email|webhook │
└──────────────┘     │ • payload           │
                     │ • retry_count        │
                     └──────────┬──────────┘
                                │ XREADGROUP
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
    ┌─────────────────┐ ┌─────────────┐ ┌──────────────┐
    │ email-worker     │ │webhook-worker│ │billing-worker│
    │ (Consumer Group │ │(CG: webhook) │ │(CG: billing) │
    │  email-proc)    │ └──────┬──────┘ └──────┬───────┘
    └────────┬────────┘       │                │
             │                │                │
             ▼                ▼                ▼
    ┌─────────────────┐ ┌───────────┐   ┌─────────────┐
    │ SMTP / Sendgrid │ │ Ext APIs  │   │ PostgreSQL  │
    └─────────────────┘ └───────────┘   │ (dedup key) │
                                        └─────────────┘
```

- Each notification type routes to a dedicated consumer group
- Billing worker writes `notification_id` to PostgreSQL before sending; skips if duplicate
- Failed messages after 5 retries route to `notifications.dlq`
- `XPENDING` + `XCLAIM` used for zombie message recovery

---

## Revision History

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 1.0 | 2026-08-04 | | Initial draft |
