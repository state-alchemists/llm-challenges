# ADR-001: Notification Subsystem — Async Processing Architecture

**Status:** Proposed

## Context

Our SaaS project management platform handles notifications (email and webhook)
synchronously inside the HTTP request cycle. As we've grown to 85,000 MAU and
~2M tasks/month, this coupling has caused request timeouts (average 800ms,
spiking to 8s), silent failures when email providers or webhook endpoints are
down, and cascading failures from slow webhook endpoints exhausting connection
pools.

We need an asynchronous notification subsystem that:

- Decouples notification delivery from the HTTP request cycle
- Supports retry with exponential backoff
- Guarantees at-least-once delivery for billing events, exactly-once where
  feasible
- Enables future WebSocket push notifications within two quarters
- Handles 10x traffic growth without re-architecting

**Constraints (the decisive ones):**

- Engineering team of 6 (3 senior, 3 mid-level), no dedicated infrastructure
  engineer
- We already operate Redis in production (session storage, rate limiting)
- Zero Kafka experience on the team today
- Must deliver value within 2 weeks of setup/migration work
- Cannot afford managed Confluent Cloud at full scale
- Exactly-once semantics required for billing notifications

## Decision

**Use Redis Streams** with consumer groups on the existing Redis infrastructure.
Supplement with a PostgreSQL-backed idempotency table for exactly-once delivery
of billing-critical notifications.

We reject Apache Kafka. It provides marginal technical advantages that do not
outweigh its operational cost for our team size, scale, and timeline.

## Consequences

### Advantages of Redis Streams

**Operational simplicity (decisive factor).** We already run Redis. The team
knows its monitoring (memory, latency, keyspace), its failure modes, and its
backup/restore procedures. Redis Streams are a data structure, not a new
daemon — no ZooKeeper or KRaft controller to manage, no broker rebalancing to
debug, no partition-assignment strategy to tune. For a team of 6 with zero
Kafka experience, this avoids a multi-week learning curve before the first
message is delivered. Estimated time to production: 3--5 days.

**Time to value.** A basic producer/consumer pattern with Redis Streams takes
hours to implement in Python (using `redis-py`'s `XADD` / `XREADGROUP`). Retry
logic with exponential backoff and a dead-letter stream can be added in another
day. We can have a working async notification pipeline in week one and iterate
in production in week two. Kafka's setup alone — cluster provisioning, topic
configuration, producer/consumer client tuning — would eat most of the 2-week
window for a team learning it from scratch.

**Scale adequacy.** Current peak is ~500 req/s, or roughly 2M notifications/month.
A single Redis instance handles 100k+ ops/s on modest hardware — two orders of
magnitude above our current peak. Even at 10x traffic growth (5,000 req/s),
Redis Streams with a single replica handle the load comfortably. At 100x we
would need to revisit, but the system must survive until then; Kafka would be
premature infrastructure at today's scale.

**Shared infrastructure for WebSocket push.** Redis pub/sub is a natural fit for
the planned real-time push notifications. Using Redis for both the stream
(durable, consumer-group-based processing) and the pub/sub channel (ephemeral
fan-out to WebSocket servers) means one data layer to operate, monitor, and
back up.

**No additional budget impact.** Redis is already in our stack. Adding streams
does not increase our AWS bill. Managed Kafka (MSK, Confluent Cloud) adds
$500--$2,000+/month even at modest throughput.

### Disadvantages of Redis Streams (and mitigations)

**No built-in exactly-once delivery.** Redis Streams offer at-least-once
(acknowledge after processing) or at-most-once (auto-acknowledge before
processing). Neither is exactly-once. However, Kafka's exactly-once semantics
(EOS) also require consumer-side idempotency in practice — the transactional
producer and consumer guarantee cross-partition atomicity, not
application-level deduplication. The correct approach is the same for both:
assign each notification a unique ID, store processed IDs in a dedup table
(PostgreSQL), and check before delivery. Our PostgreSQL instance already exists
and handles this trivially. **True exactly-once requires application-level
idempotency regardless of the transport.**

**Memory-bound storage.** Redis stores data in RAM. Streams with long retention
can exhaust memory. Mitigation: cap streams with `MAXLEN` (~10,000 entries) and
use a simple archival strategy — move processed notifications older than 7 days
to PostgreSQL or S3. The stream is a processing buffer, not a permanent event
store. This matches our actual retention requirement (billing notifications
need delivery guarantees, not permanent storage in the stream).

**No built-in partitioning.** A Redis Stream consumer group is serial per shard.
At our scale this is irrelevant — a single consumer group handles 5,000
deliveries/s without partitioning. If we ever need parallel processing of
independent streams, we can shard by notification type (billing, task-updates,
webhooks) into separate streams, each with its own consumer group.

**Larger PEL (Pending Entries List) on consumer failure.** If a consumer dies
mid-processing, its unacknowledged messages remain in the PEL. Mitigation:
monitor PEL size (`XLEN` on pending entries), set consumer timeouts via
`XCLAIM` to rebalance stale messages to healthy consumers, and alert when PEL
exceeds a threshold.

## Alternatives Considered

### Apache Kafka

**Why it was rejected.**

1. **Operational burden exceeds team capacity.** Kafka is a distributed system
   that demands dedicated operational attention: broker tuning (page cache,
   replication settings, log compaction), partition rebalancing, consumer-group
   lag monitoring, disk sizing for retention. Our team of 6 has no dedicated
   infrastructure engineer and zero Kafka experience. Adopting Kafka means
   learning a complex new stack under production pressure while also solving
   the original notification problem. This violates the 2-week delivery
   constraint.

2. **Managed Kafka is not viable.** Confluent Cloud and Amazon MSK remove some
   operational burden but add significant cost. At our current and projected
   scale (500--5,000 req/s), we would pay $500--$2,000+/month for throughput
   we do not need. The budget constraint explicitly rules this out.

3. **Exactly-once semantics are overvalued here.** Kafka's EOS guarantees
   atomic writes to multiple partitions (transactions) and prevents duplicates
   in the source topic. It does not prevent duplicate processing at the
   *consumer application* level — a crash between the consumer delivering a
   webhook and committing the offset still produces a duplicate. True
   exactly-once requires idempotent consumers with a dedup store on both
   Kafka and Redis Streams. Kafka's EOS does not eliminate this requirement.

4. **Over-engineered for the scale.** Kafka shines at 100k+ msgs/s, multi-
   consumer ecosystem, long-term event sourcing, and replay across massive
   retention windows. Our notification pipeline needs durable queuing with
   retries at 500--5,000 msgs/s — a problem Redis Streams solves trivially.
   Choosing Kafka for this workload is the distributed-systems equivalent of
   buying a cargo ship to cross a river.

5. **WebSocket push adds another system.** Kafka does not natively support
   pub/sub for WebSocket fan-out. We would still need Redis (or a separate
   channel) for real-time push, defeating the consolidation benefit.

**When we might revisit Kafka.** If traffic exceeds 50,000 req/s, if we need
long-term event sourcing with replay across months of data, or if the team
grows to include dedicated infrastructure engineers. None of these apply today.

### RabbitMQ

RabbitMQ is a mature message broker with strong routing, dead-letter exchanges,
and retry support. It was not formally evaluated because it shares Kafka's key
disadvantage — another infrastructure component to operate — without Kafka's
high-throughput upside. The team has no RabbitMQ experience either, and adding
a new broker alongside our existing Redis increases operational surface area
for marginal benefit over Redis Streams.

### Amazon SQS / SNS

SQS with SNS fan-out provides managed, highly available messaging with at-least-
once delivery and dead-letter queues. Rejected because: (a) vendor lock-in to a
single AWS region with no migration path, (b) no built-in consumer groups —
each message is read and deleted, making parallel processing coordination
harder, (c) polling latency (long-poll helps but still introduces 20ms+
overhead per batch), and (d) adding another AWS service to our bill when Redis
already sits idle-capable for this workload.
