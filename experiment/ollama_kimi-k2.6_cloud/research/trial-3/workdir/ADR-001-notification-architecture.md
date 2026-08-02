# ADR-001: Notification Architecture — Async Processing Pipeline

## Status

Proposed

## Context

Our SaaS project management platform serves 85,000 monthly active users and handles ~2M task updates per month, with peak traffic of ~500 req/s. Today, notifications (emails, webhooks) are sent synchronously inside the HTTP request cycle, causing:

- **Request timeouts**: Average notification latency of 800ms, spiking to 8s during peak hours, directly degrading user experience.
- **Silent failures**: No retry mechanism; dropped emails or failed webhook calls are lost permanently.
- **Cascading failures**: Slow or unresponsive webhook endpoints have caused connection pool exhaustion, impacting unrelated features.
- **No delivery guarantees**: Billing-critical notifications (e.g., "trial expired", "payment failed") are not guaranteed to be delivered even once, let alone exactly once.

We must decouple notification delivery from the request cycle, introduce retry with exponential backoff, and provide at-least-once delivery for all events and exactly-once semantics for billing-critical events. The solution must also support a future roadmap item—real-time WebSocket push notifications—without requiring a second technology overhaul.

**Team and operational constraints**:
- Engineering team of 6 (3 senior, 3 mid-level) with **no dedicated infrastructure engineer**.
- Already operate Redis (ElastiCache) for session storage and rate limiting.
- **No prior Kafka experience** on the team.
- Must deliver value within **2 weeks** of setup/migration work.
- **Modest budget**; managed Kafka (Confluent Cloud) at full scale is not financially viable today.
- Must support **10x traffic growth** (i.e., ~5,000 req/s peaks) without a platform replacement.

## Decision

**We will use Redis Streams as the backbone of the notification pipeline.**

Redis Streams will ingest all notification events from the Flask monolith. A set of Python worker processes (using consumer groups) will consume from the stream, dispatch emails and webhooks, and implement retry logic with a dead-letter stream. Exactly-once semantics for billing events will be enforced at the application layer using idempotency keys stored in PostgreSQL.

**Justification**: Redis Streams satisfies our functional requirements while respecting our hard operational and time constraints. Our team already runs Redis in production, so there is no net-new infrastructure to provision, secure, or monitor. We can begin event ingestion within days, not weeks. The throughput ceiling of Redis Streams (~ tens of thousands of messages per second per node) provides ample headroom for our 10x growth target (~5,000 req/s peaks, with notifications representing a fraction of total traffic). Consumer groups provide horizontal scaling of workers and automatic partitioning of load.

## Consequences

### Positive

- **Low operational overhead**: Redis is already deployed, monitored, and backed up. Adding Streams is a configuration change, not a new cluster.
- **Fast time-to-value**: The team can start prototyping within days and migrate production traffic within the 2-week window.
- **Sufficient throughput**: A single Redis node can handle an order of magnitude more throughput than our 10x target; vertical scaling (larger instance) is trivial on ElastiCache if needed.
- **Native consumer groups**: Redis Streams supports consumer groups with automatic load balancing,acknowledgments, and pending-entry lists, giving us retry and dead-letter capabilities out of the box.
- **Unified stack**: Future WebSocket push notifications (planned within 2 quarters) can use Redis Pub/Sub or Streams from the same infrastructure, avoiding a second messaging system.
- **Cost efficiency**: Uses existing ElastiCache spend; no new vendor contracts or per-partition licensing.

### Negative

- **Exactly-once is application-layer responsibility**: Redis Streams provides at-least-once delivery. Guaranteeing exactly-once for billing events requires every consumer to be idempotent. We must implement and audit idempotency keys (stored in PostgreSQL) for every billing notification handler.
- **Memory-bound retention**: Messages are held in memory (with optional persistence). Aggressive retention policies or unbounded growth could exhaust memory. We will mitigate this with explicit `MAXLEN` caps on streams and a robust dead-letter archival process to S3.
- **No built-in transactions across multiple streams**: Unlike Kafka Transactions, Redis Streams cannot atomically produce to and consume from streams in a single transaction. Our consumers must handle partial-failure edge cases carefully.
- **Operational blind spots**: Redis Streams metrics (lag per consumer group, pending message counts) are less mature in standard monitoring tools than Kafka Consumer Lag metrics. We must invest in custom CloudWatch/Redis `INFO` dashboards.
- **Partition strategy is implicit**: Redis Streams does not offer the same explicit partitioning model as Kafka; load is sharded by stream key. We will use separate stream keys (e.g., `notifications:billing`, `notifications:general`) to isolate critical traffic.

## Alternatives Considered

### Apache Kafka

Kafka was rejected despite its superior durability, mature ecosystem, and built-in exactly-once semantics (idempotent producers + Kafka Transactions), because:

1. **Operational complexity exceeds team bandwidth**: Self-hosted Kafka requires ZooKeeper (or KRaft) consensus, broker tuning, partitioning strategy design, and careful monitoring of consumer lag, ISR shrinkage, and disk usage. A 6-person team without a dedicated infrastructure engineer cannot safely own this within the required timeline.
2. **No in-house expertise**: The team has zero production experience with Kafka. A 2-week deadline does not allow for hiring, training, and hardening a new distributed system.
3. **Cost barrier for managed options**: Managed Kafka (Confluent Cloud, MSK) would eliminate operational burden but violates the modest budget constraint at projected 10x scale.
4. **Overkill for current throughput**: Our peak of ~500 req/s and even our 10x target of ~5,000 req/s are well within single-node Redis capacity. Kafka’s primary advantage—massive horizontal partitioning throughput—is not a constraint we are likely to hit before our next architectural review (18–24 months).

While Kafka is the stronger long-term strategic choice for a company with dedicated platform engineering, it is the wrong trade-off for our current team size, skill set, and delivery deadline.

---

*Submitted for review by the engineering team.*
