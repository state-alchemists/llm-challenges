# ADR-001: Notification Architecture — Adopt Redis Streams

**Status:** Proposed

## Context

The Notifier subsystem currently runs synchronously inside the Python/Flask HTTP request cycle, causing:
- Average latency of 800 ms, spiking to 8 s during peaks (~500 req/s)
- Silent drops when downstream providers fail, with no retry or dead-letter mechanism
- Cascading failures that have caused two production incidents this year
- No delivery guarantees for billing-critical events (e.g., trial expiry, payment failure)

We must decouple notification dispatch into an async pipeline that supports:
- Retry with exponential backoff
- At-least-once delivery for all events; exactly-once semantics for billing notifications
- Real-time WebSocket push within the next two quarters
- Headroom for 10× traffic growth without a second re-architecture

**Team & operational constraints**
- Engineering team: 6 people (3 senior, 3 mid-level); no dedicated SRE/infrastructure engineer
- Redis is already deployed for sessions and rate limiting
- No Kafka experience on the team
- Migration must deliver production value within two weeks
- Budget is modest; managed Kafka (Confluent Cloud, MSK Serverless at scale) is not affordable today

## Decision

**We will use Redis Streams as the core notification messaging layer.**

Redis Streams is the pragmatic choice because it meets our functional requirements while respecting our operational constraints. The team already runs Redis in production, so setup, monitoring, and on-call playbooks are largely in place. We can have a working async notification pipeline with consumer groups and retry logic in production within days, not weeks.

For the exactly-once requirement on billing notifications, Redis Streams does not provide native exactly-once semantics (unlike Kafka’s idempotent producer + transactions). We will compensate with **idempotent consumers**: each billing event carries a unique idempotency key, and the consumer records processed keys in PostgreSQL with a uniqueness constraint before performing the side effect (e.g., sending the email). This gives us effectively exactly-once delivery at the application layer, which is sufficient for our volume and acceptable given our existing PostgreSQL expertise.

Redis Streams consumer groups give us the partitioned consumption model we need for parallel processing, and Redis Pub/Sub (or a secondary WebSocket gateway layer) can be introduced later for the real-time push requirement without adding a new infrastructure category.

## Consequences

### Pros
- **Operational fit:** We already run, monitor, and back up Redis. Adding Streams uses existing tooling and on-call knowledge, reducing operational risk for a team without a dedicated infrastructure engineer.
- **Speed to value:** Streams, consumer groups, and retry logic can be deployed within days, satisfying the two-week delivery constraint.
- **Cost:** Uses the existing Redis cluster (with appropriate AOF and RDB persistence enabled); no new managed-service bill or additional VM footprint.
- **Consumer groups:** Native support for consumer groups (since Redis 5.0) provides partitioned consumption, automatic acknowledgment tracking, and claim-on-failure for stalled messages.
- **Ordering guarantees per stream:** Events within a single stream key are strictly ordered, which simplifies sequencing logic for per-user or per-task notification threads.
- **Unified platform:** Redis Pub/Sub and Streams live on the same infrastructure we will later leverage for WebSocket push, keeping the real-time stack homogeneous.

### Cons
- **Throughput ceiling:** Redis Streams is memory-bound and single-node primary (or primary-replica with failover). While adequate for our current 500 req/s and 10× growth, it will eventually hit a wall well before Kafka would. If we grow past that, we will need to shard streams by tenant or re-evaluate.
- **Retention complexity:** Message retention is governed by Redis memory limits and `MAXLEN` trimming policies, not by time-based retention with cheap disk storage. We must actively cap stream lengths or move processed events to cold storage to avoid OOM.
- **Exactly-once is application-level:** We must build and maintain idempotency tracking in PostgreSQL for billing events. This adds a small but critical code path that must be audited and tested; a native exactly-once streaming primitive would be preferable.
- **Disk persistence model:** Redis relies on AOF and periodic RDB snapshots. A catastrophic failure immediately after an ACK but before an AOF fsync could still lose a small window of acknowledged messages. We will mitigate this with `appendfsync always` on the relevant Redis instance and by accepting at-least-once for non-billing events.
- **No replay from arbitrary offsets by time:** Replay is stream-relative. Historical reprocessing for analytics or debugging requires us to archive messages to S3 or PostgreSQL as a side effect.

## Alternatives Considered

### Apache Kafka

Kafka was rejected primarily due to **operational complexity and time-to-value**, not because it is technically inferior.

Kafka objectively outperforms Redis Streams on several dimensions relevant to our problem:
- **Throughput:** Kafka is designed for millions of events per second across many partitions; Redis Streams tops out at tens of thousands per node.
- **Retention:** Kafka stores messages on cheap disk with configurable time-based retention (days, weeks, or indefinite); Redis Streams is memory-first.
- **Consumer groups & rebalancing:** Kafka’s consumer-group protocol is more mature, supporting dynamic rebalancing and automatic partition assignment at scale.
- **Exactly-once semantics:** Kafka provides native exactly-once processing via idempotent producers and transactions, which would eliminate the need for application-level idempotency tracking.

However, for our team and timeline these strengths are outweighed by:
1. **Operational overhead:** Running a production Kafka cluster (even a small 3-broker setup with ZooKeeper or KRaft) requires expertise in partition rebalancing, broker maintenance, and failure recovery that our 6-person team does not have today.
2. **Learning curve:** No engineer on the team has production Kafka experience. A two-week migration is not credible when it must include cluster provisioning, client library integration, producer/consumer tuning, exactly-once configuration, and on-call training.
3. **Cost:** A managed offering (Confluent Cloud, Amazon MSK) that hides operational complexity is outside our modest budget. Self-hosting saves money but consumes engineering time we do not have.
4. **Over-engineering risk:** Kafka’s power is meaningful at multi-thousand-event-per-second sustained throughput and long-term retention. Our current peak is 500 req/s and our 10× target is still well within the operating envelope of a properly sized Redis node.

Because our most acute risks are **delivery reliability within the next two weeks** and **operational sustainability without an SRE**, Kafka’s long-term scalability advantages do not justify the upfront cost and risk. We will revisit Kafka if we outgrow Redis Streams or hire dedicated infrastructure expertise.
