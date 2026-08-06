# ADR-001: Asynchronous Notification Delivery Using Redis Streams

## Status

Proposed

## Context

Notifications (email, webhooks) are currently sent synchronously inside the
Flask request cycle, and this is the root cause of the four problems in
`system_context.md`:

1. **Request timeouts** — sending blocks the response; average latency 800 ms,
   spikes to 8 s at peak.
2. **Silent failures** — a down email provider or webhook endpoint drops the
   notification with no retry and no dead-letter queue.
3. **Cascading failures** — a slow webhook exhausted the connection pool twice
   this year and took down unrelated features.
4. **No delivery guarantees** — billing-critical notifications ("trial
   expired", "payment failed") need exactly-once delivery and have no
   guarantee at all.

The subsystem must be decoupled from the HTTP cycle and provide: asynchronous
processing, retry with exponential backoff, at-least-once delivery for billing
events (exactly-once where feasible), real-time WebSocket push within two
quarters, and headroom for 10x traffic without re-architecting.

Hard constraints on the solution:

- Engineering team of 6 (3 senior, 3 mid), no dedicated infrastructure
  engineer.
- Redis is already in production for session storage and rate limiting; there
  is **no Kafka experience on the team**.
- Setup/migration must deliver value in **no more than 2 weeks**.
- Budget is modest — managed Confluent Cloud is out of reach at full scale.
- Exactly-once semantics must hold for billing notifications.

Load profile (derived from `system_context.md`): ~2M notifications/month
≈ 0.8 events/s average; peak 500 req/s implies a few thousand events/s at
peak; 10x growth implies a worst-case peak in the low tens of thousands of
events/s.

## Decision

Adopt **Redis Streams** as the notification delivery backbone.

Notifications are published with `XADD` inside the request handler (a local,
sub-millisecond Redis operation that removes the external HTTP dependency from
the request path) and consumed asynchronously by a small worker pool using
Redis consumer groups (`XREADGROUP` / `XACK` / `XAUTOCLAIM`). Failed deliveries
are retried with exponential backoff and eventually moved to a dead-letter
stream. Billing events are processed idempotently using the stream entry ID as
the deduplication key.

This decision is driven by the constraints, not by a feature comparison in a
vacuum: at this scale the two technologies are functionally equivalent, and
Redis Streams wins on every constraint that is actually binding — team size,
existing infrastructure, delivery deadline, and budget.

**Why the requirements are met:**

- **Decoupling.** `XADD` is a single local Redis call in the request path;
  the 800 ms–8 s external send moves to workers. The request cycle no longer
  depends on the availability of email/webhook providers, which also
  eliminates the connection-pool exhaustion cascade.
- **At-least-once delivery.** Consumer groups track a per-consumer pending
  entries list (PEL); an entry is only removed when the worker `XACK`s it
  after the side effect (email/webhook call) succeeds. A worker that crashes
  mid-delivery leaves the entry pending, and `XAUTOCLAIM` reassigns it to a
  healthy consumer after a timeout. Retry with exponential backoff is a
  re-enqueue loop with a delay; a separate stream serves as the dead-letter
  queue with no extra infrastructure.
- **Exactly-once for billing.** This deserves an honest statement: neither
  Redis Streams nor Kafka can deliver true end-to-end exactly-once to an
  external side effect (an email provider or webhook endpoint). Kafka's
  exactly-once semantics guarantee atomicity *inside Kafka* (transactions
  across topics); the final external call is still at-least-once in both
  systems. The only way to reach exactly-once end-to-end is an idempotent
  consumer keyed on an event ID. Redis Streams gives us that key for free —
  entry IDs are unique and monotonically increasing — so billing handlers
  deduplicate on the stream ID. The billing requirement is therefore met by
  at-least-once delivery plus idempotent processing, which is the industry
  standard pattern and is achievable in days rather than the weeks Kafka's
  transactional tooling would take to stand up correctly.
- **Ordering.** Entries in a stream are totally ordered by their auto-generated
  ID (`<milliseconds>-<sequence>`). Per-task ordering (e.g., "assigned" must
  not overtake "completed") is preserved by sharding: one stream per entity
  key or one consumer per stream, exactly the same discipline Kafka requires
  with partitions.
- **Throughput headroom.** A single Redis instance sustains on the order of
  100k+ `XADD`/`XREADGROUP` operations per second on modest hardware — an
  order-of-magnitude figure to be confirmed by a benchmark, but the point is
  the ratio: our 10x worst-case peak (~tens of thousands of events/s) leaves
  at least 5x headroom on the Redis instance we already run. Kafka's millions
  of messages per second is a capability we do not need.
- **Retention.** Notification events are transient: they live for the retry
  window (minutes to days) and the DLQ inspection window, not for long-term
  replay. Redis Streams trims with `XADD ... MAXLEN ~ <N>`; at a few hundred
  bytes per entry, a 200k-entry cap is tens of MB per stream — negligible
  against the existing session cache. Postgres remains the system of record
  for the durable audit trail.
- **WebSocket push (2-quarter target).** The same Redis instance already in
  the architecture supports the natural fan-out pattern: publish to a channel
  with Pub/Sub, and every WebSocket server instance forwards to its connected
  clients. No second technology is introduced.
- **Delivery timeline.** `XADD` in the request path is a drop-in replacement
  for the synchronous send; a worker can consume from the stream the same day.
  Value lands in days, comfortably inside the 2-week cap. Standing up and
  learning Kafka from scratch — brokers, partitions, consumer groups,
  rebalancing, monitoring, exactly-once gotchas — realistically exceeds the
  cap for a team with zero Kafka experience.

## Consequences

### Pros

- **No new infrastructure.** Streams are a data structure on the Redis we
  already run for sessions and rate limiting. No new services, no new
  monitoring surface, no new failure domain.
- **Fits the team.** The 6-person team already operates Redis in production;
  the operational burden is incremental, not new. No Kafka skill acquisition
  is required, and no dedicated infrastructure engineer is needed.
- **Fast delivery.** The synchronous-to-asynchronous cutover is days of work,
  well inside the 2-week constraint, and the first benefit (removing the
  800 ms blocking send) lands immediately.
- **At-least-once with retry and DLQ built on existing primitives.** PEL +
  `XACK` gives delivery tracking; `XAUTOCLAIM` gives crash recovery;
  exponential backoff is a delay loop; the DLQ is just another stream.
- **Exactly-once-for-billing achieved via idempotent handlers keyed on the
  stream entry ID** — the only mechanism that works end-to-end in any
  architecture, with the unique ID supplied by Redis at no cost.
- **Throughput headroom.** Roughly 5x+ margin over the 10x traffic target on a
  single instance, so no re-architecture is triggered by the stated growth
  goal.
- **Failure isolation.** The request path depends only on local Redis, so a
  slow webhook can no longer exhaust the connection pool or time out the
  response.
- **WebSocket fan-out reuses the same infrastructure** via Pub/Sub, meeting
  the 2-quarter target without a second system.

### Cons

- **Memory-bound retention.** Streams live in RAM, so retention is limited by
  memory sizing rather than disk. Long-term replay and log compaction are not
  available; we must trim with `MAXLEN` and keep the durable audit trail in
  Postgres. Kafka's disk-based retention would be strictly better here, but we
  do not need long replay for notifications.
- **Exactly-once is a discipline, not a feature.** We must implement and test
  idempotent billing handlers; Redis gives us the dedup key, not the
  guarantee. Kafka's transactional API is a more mature in-broker story, but
  as noted it does not extend end-to-end either, so this is a shared
  requirement, not a Redis-specific penalty.
- **No cross-stream atomicity.** There is no transaction that atomically
  publishes to a stream and commits an external side effect. This is a
  limitation of every message broker with respect to external systems; Kafka's
  transactions only span Kafka topics. Idempotency, not atomicity, is the
  answer in both cases.
- **Delayed delivery must be built.** Backoff scheduling is our own small
  component (e.g., a sorted-set-based delayed queue feeding back into the
  stream). Kafka has no native delayed delivery either, so this cost is equal
  across both options.
- **Capacity is RAM-bound and single-writer.** The stream's ceiling is the
  memory of one Redis instance; exceeding it means moving to Redis Cluster,
  which adds real operational complexity. At 10x target load we are an order
  of magnitude below that ceiling, but this must be re-visited if traffic
  outstrips the projection.
- **Team must learn the Streams API** (`XADD`, `XREADGROUP`, `XACK`,
  `XAUTOCLAIM`, PEL semantics). This is a small, days-long learning curve —
  materially smaller than Kafka's — but it is new.

## Alternatives Considered

**Apache Kafka — rejected.**

Kafka's strengths are real and well understood: disk-based retention with log
compaction, extremely high throughput (millions of messages/s), mature
consumer-group rebalancing, and the industry's most sophisticated
exactly-once tooling (idempotent producers, transactional consumers). None of
these are decisive for this workload, and three of the four are irrelevant at
our scale: a few thousand events/s at peak does not need Kafka's throughput;
transient notifications do not need disk retention or compaction; and Kafka's
exactly-once is confined to inside the broker, so the billing requirement
still lands on idempotent consumers — exactly the same pattern Redis requires.

What Kafka *does* cost us is the binding constraint set:

- **Operational complexity.** Self-hosting Kafka means brokers, partition and
  replica management, rebalancing behavior, offset and retention tuning, and
  dedicated monitoring — a full-time concern for an organization with no
  dedicated infrastructure engineer and no Kafka experience.
- **Budget.** Managed Confluent Cloud is explicitly out of reach; AWS MSK
  (minimally a 3-broker cluster plus storage and data-transfer costs) is a
  meaningful recurring line item for a modest budget and still demands
  Kafka-specific expertise to operate correctly.
- **Timeline.** Standing up Kafka, and getting a team of six to *correctly*
  build on consumer-group semantics, partitioning, and exactly-once
  transaction handling, exceeds the 2-week delivery cap. Redis Streams
  delivers value in days.
- **New infrastructure, new failure domain.** Kafka is a second distributed
  system to run, monitor, and restore; the whole point of this change is to
  *reduce* the coupling and operational surface of notifications, and adding
  a broker cluster works against that.

Kafka is the right answer when we outgrow Redis Streams — if throughput
demands exceed a single Redis instance by a wide margin, if we need long-term
event replay or a cross-team event platform, or if the organization gains a
platform team with Kafka expertise. None of those conditions hold today, and
the decision records them explicitly so the choice is re-opened when one of
them does.
