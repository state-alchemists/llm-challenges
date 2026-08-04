# ADR-001: Notification Subsystem — Asynchronous Delivery with Redis Streams

## Status

Proposed

## Context

We run a SaaS project management platform: 85,000 monthly active users, ~2M tasks created per month, and a peak of ~500 requests/second. The backend is a Python/Flask monolith (~50k lines) on four web servers behind an nginx load balancer, with PostgreSQL as the source of truth and Redis already in production for session storage and rate limiting.

Today the notifications module sends emails and webhooks synchronously inside the HTTP request cycle. As usage has grown this has produced four concrete failures:

1. **Request timeouts.** Notification I/O blocks the response; average latency is 800ms and spikes to 8s during peak hours.
2. **Silent failures.** If the email provider or a webhook endpoint is down, the notification is dropped. There is no retry and no dead-letter queue.
3. **Cascading failures.** Twice this year a slow webhook endpoint exhausted the PostgreSQL connection pool and took down unrelated features.
4. **No delivery guarantees.** Billing-critical notifications ("trial expired", "payment failed") must be delivered exactly once; today they are best-effort.

The target architecture must decouple notifications from the HTTP request cycle, retry with exponential backoff, guarantee at-least-once delivery (and exactly-once where feasible), add real-time WebSocket push within two quarters, and absorb 10x traffic growth without re-architecting.

Constraints that shape this decision:

- The engineering team is six people (three senior, three mid-level) with no dedicated infrastructure engineer.
- Redis is already operated in production; Kafka is not running anywhere and nobody on the team has operated it.
- The new pipeline must deliver value within two weeks of starting, including setup and migration.
- The budget is modest; managed Confluent Cloud is not affordable at full scale today.
- Exactly-once semantics for billing notifications are non-negotiable.

## Decision

We choose Redis Streams as the notification backbone. Producers will append notification events to sharded streams; worker processes will consume them via Redis consumer groups and deliver to email providers, webhook endpoints, and (later) the WebSocket gateway. The pipeline is at-least-once by design; exactly-once behavior for billing events comes from a transactional outbox and idempotent consumers, described below.

The load math settles the throughput question quickly. Roughly 2M tasks are created per month, and each task update fans out to a handful of notifications — call it 5–10M notifications/month, a few hundred thousand per day. Even at 10x traffic concentrated in business hours, peak throughput is on the order of 10³ messages/second. A single Redis instance sustains 100k+ operations per second on modest hardware, and Streams commands can be pipelined and batched; the broker will not be the bottleneck at 10x. Kafka is capable of millions of messages per second on a modest cluster — capability three orders of magnitude beyond what this workload will ever ask of it, at the price of a distributed system we would have to run and learn.

Ordering: both systems preserve insertion order only within a shard consumed by a single worker. With Redis we shard by task_id (a fixed set of streams, one active consumer per stream) so that notifications for a given task are delivered and processed in order; with Kafka the same guarantee comes from partitioning by key. Neither system gives global ordering across parallel consumers, and this application does not need it.

Exactly-once is the requirement people most often reach for Kafka to satisfy, and it does not actually differentiate the two options here. Kafka's exactly-once semantics (idempotent producer plus transactions, KIP-98) guarantee atomicity *within the Kafka ecosystem*: a consumer's reads from and writes to Kafka can be transactional. They do not cover the side effect that matters to us — an HTTP POST to a webhook or an email API call. The provider sits outside the transaction; if the network drops the request after the provider committed it, no broker can prevent a duplicate. Achieving exactly-once delivery to external systems therefore requires the same pattern on either broker: a transactional outbox in PostgreSQL (the notification intent committed atomically with the business change that created it), a relay that publishes outbox rows to the stream, and idempotent consumers that deduplicate on a notification_id key before the side effect. That pattern gives effectively-once delivery — the strongest guarantee any external API can actually honor — and it is broker-agnostic. Kafka's flagship feature buys us nothing we would not have to build ourselves on top of Redis Streams.

Operational complexity is where the decision is settled. Redis Streams is a data structure on a service we already run; the migration is a few days of work — new streams, consumer-group code, an outbox table, a worker process — and it adds no new service to the stack. Kafka is a distributed log: brokers, KRaft, partitions and replication, rebalancing, consumer-lag monitoring, disk sizing, and JMX metrics, none of which this team has run before. With six engineers and no infrastructure specialist, self-hosting Kafka is a permanent operational tax, and the budget rules out Confluent Cloud. The two-week constraint alone eliminates Kafka: standing it up, hardening it, and learning its semantics would consume the budget before any notification moved through it.

Redis also positions us correctly for the WebSocket requirement in the next two quarters. Four web servers need cross-node fan-out so a push event reaches the right connection wherever it lives; Redis Pub/Sub and Streams are the standard mechanism for that (e.g., the Socket.IO Redis adapter). Choosing Redis Streams keeps queued notifications and live push on one backbone instead of running two infrastructure systems.

## Consequences

### Pros

- **Fast time-to-value.** Streams are a feature of infrastructure we already run; the outbox + worker pipeline can ship in well under the two-week constraint. No new vendor, no new service, no procurement.
- **Low operational burden.** Consumer groups, acknowledgment, and redelivery are built in (XGROUP, XACK, XPENDING, XAUTOCLAIM). A six-person team with no infrastructure engineer can operate this — one Redis instance with AOF enabled, not a cluster.
- **At-least-once with retry built in.** Unacknowledged messages stay in each consumer group's pending list; XAUTOCLAIM reassigns entries after an idle timeout, which is the hook for exponential backoff, and a dead stream serves as the DLQ.
- **Ordering per task via sharding.** task_id sharding across streams gives per-task ordering with parallel workers, matching Kafka's per-partition guarantee.
- **Headroom for 10x.** The workload at 10x (10³ msg/s) is two orders of magnitude below what a single Redis node sustains; we do not need a cluster to meet the stated target.
- **One backbone for push and queues.** The same Redis instance (or a dedicated streams instance) fans out to WebSocket gateways, keeping the stack small.
- **A migration path that stays open.** Because the outbox pattern is broker-agnostic, moving to Kafka later — should we outgrow Redis or need long retention and replay — requires changing the relay, not the producers or consumers.

### Cons

- **Retention is bounded by length, not time.** Streams are trimmed with MAXLEN or MINID; there is no per-message TTL. A burst can evict unconsumed entries if the cap is sized too small. We must size the cap to cover the worst-case retry window and treat the PostgreSQL outbox, not the stream, as the durable record.
- **Redis is memory-first.** Without AOF, a restart can lose messages since the last snapshot. We must enable AOF (appendfsync everysec) and accept up to ~1s of loss on a crash; the outbox makes that loss recoverable.
- **Single-instance ceiling and SPOF.** A single Redis node is fine at 10x but is a single point of failure; moving to Redis Cluster for more capacity or high availability raises operational complexity and adds cross-slot constraints. We mitigate with replication and monitoring, not by pretending the failure mode is absent.
- **No ecosystem.** Kafka ships with Schema Registry, Connect, and stream processing (Kafka Streams); Redis Streams is a data structure. If the platform grows into event sourcing or analytics over the event bus, we would build tooling Kafka gives us for free.
- **Exactly-once is still work.** Redis Streams alone gives at-least-once; the billing guarantee comes from the outbox and idempotent consumers, which we must build and test. There is no configuration flag that makes it appear.
- **A small learning curve.** Consumer-group semantics (PEL, XAUTOCLAIM, acking) are new to the team — days, not weeks, and far less than Kafka.

## Alternatives Considered

### Apache Kafka — rejected

Kafka is the industry-standard event backbone and the technically stronger system in the abstract: a true distributed log with time- and size-based retention, replay from arbitrary offsets, mature consumer groups with rebalancing, and exactly-once semantics within its own ecosystem. We rejected it for this system because its strengths are not the ones this problem needs, and its costs are ones we cannot pay:

- **Operational complexity vs. team size.** Kafka is a distributed system to run — brokers, KRaft, partitioning and replication decisions, rebalancing, consumer-lag monitoring, disk throughput, retention tuning. Nobody on the six-person team has operated it, and there is no infrastructure engineer to own it. Self-hosting Kafka at our scale is a second full-time job on a team that has none to spare.
- **Cost.** Confluent Cloud is outside the budget at the scale we would need. Amazon MSK reduces the mechanical burden but still requires operating Kafka semantics and monitoring, and adds meaningful cost.
- **Throughput overkill.** Kafka's millions of messages per second serve workloads ours will never approach; we need 10³/s at 10x. Paying a distributed system's complexity for headroom we cannot use is not a trade we should make.
- **Exactly-once does not extend to external side effects.** This is the argument that most often justifies Kafka for billing-critical work, and it does not survive contact with the actual system: email providers and webhook endpoints sit outside the broker's transaction scope. Delivering to them exactly once still requires the outbox + idempotency pattern we would build on Redis. Kafka's EOS is not a substitute for that work.
- **Ordering parity.** Per-partition ordering in Kafka is equivalent to per-stream ordering via task_id sharding in Redis; no advantage either way.
- **Retention and replay are genuinely better in Kafka** — time-based retention and offset replay are real advantages. They are not requirements for notifications: the outbox provides durability, and nobody needs to replay last month's webhooks.

Kafka becomes the right choice when the platform itself becomes an event bus: sustained throughput above ~10⁵ msg/s, multiple independent consumers of the same events with different retention needs, event sourcing, or analytics pipelines over the log. None of that is true today. The outbox abstraction deliberately keeps that migration affordable if it ever becomes true.

### AWS SQS/SNS — briefly evaluated

AWS SQS/SNS is cheap, fully managed, and operationally trivial, and we rejected it on two properties. Standard queues deliver at-least-once with no ordering, which breaks per-task notification ordering; FIFO queues restore ordering but cap throughput at roughly 300 messages/second per message group (3,000 with batching), which a 10x fan-out of webhooks can exceed. It would also split the stack across a second vendor when Redis is already in the building. It remains a reasonable fallback for the DLQ tier of the Redis pipeline if we ever want managed retry storage.
