# ADR-001: Notification Subsystem Architecture

**Status:** Proposed

## Context

Our SaaS project-management platform serves 85,000 monthly active users and creates ~2M tasks per month. Notification delivery (emails and webhooks) is currently handled synchronously inside the Python/Flask HTTP request cycle. At peak load (~500 req/s) this produces:

- **Request timeouts** — average notification latency 800ms, spiking to 8s, because callers wait for SMTP and HTTP webhook round-trips.
- **Silent failures** — no retry or dead-letter mechanism when an email provider or webhook endpoint is down.
- **Cascading failures** — slow webhook endpoints have twice caused connection-pool exhaustion and monolith-wide outages.
- **No delivery guarantees** — billing-critical notifications (trial expired, payment failed) are emitted exactly once by application code, but network or provider failures can drop them with no recovery path.

We must move notification dispatch to an asynchronous, durable message-bus architecture that supports:

1. Decoupled, async processing (remove notification work from the HTTP path).
2. Retry with exponential backoff.
3. At-least-once delivery for general notifications; exactly-once semantics for billing events.
4. A migration completed within two weeks before delivering production value.
5. Capacity for 10x traffic growth (~5,000 req/s equivalent notification load) without another re-architecture.

**Constraints**

- Engineering team: 6 people (3 senior, 3 mid-level); no dedicated infrastructure engineer.
- Redis is already operational (sessions, rate limiting).
- No team member has production Kafka experience.
- Budget is modest; managed Kafka (Confluent Cloud) is unaffordable at target scale.
- The billing domain requires an exactly-once guarantee, which rules out naive at-least-once retry unless we add application-level idempotency.

## Decision

We will use **Redis Streams** as the messaging backbone for the notification subsystem.

**Justification**

| Property | Redis Streams | Apache Kafka |
|---|---|---|
| **Throughput** | Single-node Redis Streams routinely exceeds 100,000 messages/sec. Our 10x target (~5,000 notification events/sec at peak) is two orders of magnitude below that ceiling. | Higher aggregate throughput with partitioning, but that headroom is irrelevant at our scale and adds operational overhead we cannot absorb. |
| **Ordering guarantees** | Redis Streams preserves strict FIFO ordering per stream key. We will shard by notification category (`stream:email`, `stream:webhook`, `stream:billing`) so ordering is maintained where it matters. | Partition-level ordering is stronger for massive parallelism, but our stream-sharding strategy gives us equivalent ordering semantics for the volumes we handle. |
| **Message retention** | `MAXLEN` / `MINID` trimming plus AOF persistence gives us days of retention with O(1) insertion. Notifications are ephemeral: consumers process within minutes and only need a short retry window; we do not require multi-week disk retention. | Durable, disk-based log retention is superior on paper, yet the extra retention duration is unnecessary for notifications and would force us to manage disk sizing and log compaction topics we do not need. |
| **Consumer groups** | Native `XGROUP CREATE`, `XREADGROUP`, and `XACK` provide automatic load balancing across consumers, pending-entry lists for automatic redelivery, and straightforward back-pressure via blocking reads. | Consumer groups with partition rebalancing are more feature-rich, but the rebalancing protocol and partition-count tuning introduce failure modes (rebalance storms, offset-management bugs) that a team without Kafka experience is ill-equipped to debug. |
| **Exactly-once semantics** | Native at-least-once delivery (`XACK` after processing). For billing events we will supplement this with **application-level idempotency**: every billing message carries a deterministic UUID (event ID); the consumer writes the outcome to PostgreSQL using an `INSERT … ON CONFLICT DO NOTHING` idempotency table inside the same local transaction that dispatches the notification. This yields practical exactly-once processing without requiring distributed transaction infrastructure. | Native exactly-once (idempotent producers + transactions + transactional consumer offset commits) is the industry gold standard, but configuring, tuning, and operating it safely requires deep Kafka expertise we do not possess. |
| **Operational complexity** | Redis is already deployed, monitored (metrics, alerting, backup), and staffed. Adding Streams is a configuration change, not a new system. Failover, persistence, and scaling patterns are already understood by the team. | A self-managed Kafka cluster (ZooKeeper or KRaft, broker tuning, replication factors, partition planning, ISR management, separate monitoring) would demand weeks of ramp-up and ongoing on-call burden that our 6-person team cannot sustainably carry. Managed Kafka is ruled out by budget. |

The decisive factors are **time-to-production** and **operational risk**. We have a hard two-week migration window and no infrastructure engineer. Redis Streams lets us meet the delivery-guarantee, retry, and throughput requirements within that window using infrastructure we already trust. Kafka would likely force us to spend the two weeks merely standing up and learning the cluster, leaving no time to ship the decoupled notification pipeline that solves the immediate outage risk.

## Consequences

### Positive

- **Fast migration**: We can go from prototype to production in days because the transport layer requires no new hosts, networks, or runbooks.
- **Familiar operations**: On-call engineers already know how to handle Redis failover, memory pressure, and AOF recovery.
- **Sufficient headroom**: 100k+ msgs/sec per node gives us runway well past 10x growth.
- **Built-in retry mechanics**: Pending-entry lists and `XPENDING` / `XCLAIM` give us dead-letter and redelivery semantics out of the box.
- **Unified infrastructure**: One less data store to patch, monitor, and pay for.

### Negative

- **Exactly-once is not native**: We must implement and audit idempotency logic in every billing consumer. A bug in the deduplication table or a mis-ordered commit could duplicate or drop a billing event. This risk is mitigated by keeping the idempotency schema small and covered by unit/integration tests, but it is still application-level complexity Kafka would have absorbed.
- **Memory-bound retention**: Long-term replay or audit trails are impractical in Redis. We will archive processed billing outcomes to PostgreSQL for compliance, but the stream itself cannot serve as a long-term event log.
- **Weaker ecosystem**: We will write our own retry/back-off wrapper and observability hooks rather than leveraging mature stream-processing frameworks (e.g., Kafka Streams, ksqlDB).
- **Future re-evaluation**: If the product grows to tens of thousands of events per second with complex stream joins or if we need months of durable retention, we will likely need to revisit this decision and migrate to Kafka. Redis Streams is the right choice for the next 18–24 months, not necessarily forever.

## Alternatives Considered

### Apache Kafka — Rejected

Kafka was the first alternative we evaluated because of its strong exactly-once semantics and its reputation for high-throughput, durable messaging. In a vacuum it is the technically superior log-based messaging system.

We rejected it because of **operational mismatch with our constraints**:

1. **Team expertise gap**: No engineer on the team has operated Kafka in production. Self-managed Kafka has a long, well-documented learning curve (broker configuration, partition/replica balancing, consumer lag diagnosis, ISR shrinkage). Without a dedicated infrastructure engineer, the on-call burden would fall on feature developers and likely degrade reliability rather than improve it.
2. **Migration timeline**: Two weeks is insufficient to stand up a production-grade Kafka cluster, configure exactly-once producers/consumers, write new runbooks, and migrate the notification pipeline while continuing to ship other work.
3. **Budget**: Managed Kafka (Confluent Cloud, MSK) would remove the operational burden but is explicitly out of budget at our expected scale. Self-hosted is the only viable path, compounding the expertise problem.
4. **Over-engineering for current scale**: Kafka’s strengths (partition-level parallelism, petabyte-scale retention, stream-processing frameworks) solve problems we do not yet have. Redis Streams meets our 10x throughput target and our delivery-guarantee needs when paired with application-level idempotency.

We will re-evaluate Kafka if we outgrow Redis Streams operationally or if we hire dedicated infrastructure expertise.
