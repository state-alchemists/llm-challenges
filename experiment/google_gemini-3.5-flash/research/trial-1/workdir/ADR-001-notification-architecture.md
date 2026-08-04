# Title: ADR-001 - Notification Subsystem Architecture

## Status
Proposed

## Context

### Current Scale & Infrastructure
We operate a SaaS project management platform serving 85,000 Monthly Active Users (MAU). We process approximately 2 million tasks created per month, with peak traffic reaching ~500 requests per second (req/s) during business hours. 
Our technical stack consists of:
*   **Backend**: Python/Flask monolith (~50k LOC)
*   **Database**: PostgreSQL (single primary, one read replica)
*   **Infrastructure**: 4 web servers behind an Nginx load balancer, hosted on AWS
*   **Cache**: Redis (currently utilized for session storage and rate limiting)

### The Problem
The notifications module (sending emails and webhooks for task updates, assignments, and completions) is currently executed synchronously within the HTTP request cycle. This has introduced several critical failure modes:
1.  **Request Timeouts**: Blocking the HTTP response to execute network calls (emails/webhooks) results in an average latency of 800ms, spiking to over 8s during peak hours, degrading user experience.
2.  **Silent Failures & Dropped Events**: Temporary downtime of email providers or third-party webhook endpoints results in dropped notifications. There is no retry mechanism, queueing, or Dead-Letter Queue (DLQ).
3.  **Cascading Failures**: Connection pool exhaustion has occurred twice this year because slow or timing-out third-party webhook endpoints blocked Flask thread execution, causing full platform outages.
4.  **No Delivery Guarantees**: Billing-critical events (e.g., "trial expired", "payment failed") have no reliability mechanisms, whereas they must be processed reliably and exactly once where feasible.

### Scaling & Business Constraints
*   **Performance Target**: Decouple notification delivery from HTTP request cycles via asynchronous processing and support 10x traffic growth (~5,000 req/s) without re-architecting.
*   **Functional Requirements**: Implement retry loops with exponential backoff, establish real-time WebSocket push notifications within 2 quarters, and guarantee at-least-once delivery for billing events (exactly-once processing semantics).
*   **Resource Constraints**: The engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer or DevOps support.
*   **Time-to-Market**: Setup, deployment, and initial migration must take less than 2 weeks of engineering effort before delivering production value.
*   **Budget & Tech Debt**: The budget is modest; enterprise managed streaming (such as Confluent Cloud) is financially unfeasible. The team has zero experience operating or developing against Apache Kafka, but already runs and monitors Redis in production.

---

## Decision

We will use **Redis Streams** as the message broker for our new asynchronous notification subsystem, utilizing our existing Redis infrastructure.

### Comparison of Technical Properties

| Technical Property | Apache Kafka | Redis Streams | Evaluation & Relevance to our Constraints |
| :--- | :--- | :--- | :--- |
| **Throughput** | Scalable to millions of events/sec via distributed partitioning. Massive overkill for our scale. | Easily handles tens of thousands of ops/sec (in-memory). Ideal for our 10x target of 5,000 req/s. | **Redis Streams Wins**: Easily handles our current and future traffic targets with sub-millisecond response times and minimal system resources. |
| **Ordering Guarantees** | Guaranteed within a partition. Requires key-based routing (e.g., hashing by `task_id` or `user_id`). | Chronological event appending by default inside the stream using timestamp-sequence IDs (`time-seq`). | **Tie**: Both support strict chronological ordering, preventing race conditions (e.g., processing "task assignment" before "task creation"). |
| **Message Retention** | Disk-backed, configurable retention (e.g., 7 days or infinite) with zero RAM pressure. | In-memory storage. Requires active stream size capping (`MAXLEN`) to prevent RAM exhaustion. | **Kafka Wins**: Kafka offers durable long-term storage, but Redis Streams is fully sufficient when capped and paired with a persistent PostgreSQL log. |
| **Consumer Groups** | Built-in partition-based consumer balancing. High complexity, susceptible to rebalance storms. | Built-in via `XGROUP`, `XREADGROUP`, client-managed pending list (`XPENDING` and `XCLAIM`). | **Redis Streams Wins**: Redis's client-driven approach avoids Kafka's complex coordinator state, making worker scaling lightweight and simpler. |
| **Exactly-Once Semantics (EOS)** | Supported natively via internal transactional APIs (producers, coordinators). | Achieved via outbox/idempotency patterns combined with PostgreSQL database transactions. | **Tie (with context)**: Kafka's EOS is redundant because our side-effects (sending emails/webhooks) are external. PostgreSQL-level deduplication is mandatory under either option. |
| **Operational Complexity** | Extremely high. Requires managing JVMs, ZooKeeper/KRaft, disk IO, partition replication. | Near zero. Already deployed, monitored, and scaled in production by our 6-person team. | **Redis Streams Wins**: Zero infrastructure setup/costs, easily fitting our 2-week time-to-market and modest budget constraints. |

### Justification
Redis Streams provides the optimal balance of throughput, simplicity, and low operational overhead, enabling us to deliver the decoupled architecture within our 2-week deadline and modest budget. 

1.  **Alignment with Resource Constraints**: With only 6 engineers and no dedicated infrastructure specialist, self-hosting Kafka is a severe operational risk. Managed Kafka is rejected due to budget limitations. Since Redis is already operated in production, adoption requires no new infrastructure, zero bootstrap time, and zero learning curve.
2.  **Guaranteed Exactly-Once Processing (EOP)**: True exactly-once *delivery* to external APIs (e.g., SendGrid, custom webhooks) is a distributed systems impossibility because external network calls cannot participate in database transactions. However, exactly-once *processing* within our system is achieved by coupling Redis Streams with our persistent PostgreSQL database. By processing notifications inside PostgreSQL transactions using a unique event deduplication table (the Outbox and Idempotent Consumer patterns), we satisfy the billing safety requirements without needing Kafka's complex transactional coordination.
3.  **Low Latency & Scalability**: At our 10x scaling target of 5,000 req/s, Redis Streams easily processes the load on a single moderate instance with sub-millisecond latency, freeing up HTTP threads instantly.

---

## Consequences

### Positive (Pros)
*   **Minimal Setup Time**: Integrating Redis Streams takes less than 2 days of configuration, easily fitting within the 2-week limit.
*   **No Infrastructure Cost Increase**: We can leverage our existing AWS-hosted Redis cluster (e.g., ElastiCache), avoiding the cost of a managed Kafka provider or the infrastructure overhead of self-hosting Kafka.
*   **Extremely Low Latency**: In-memory queuing ensures that appending to the stream (`XADD`) is highly performant (<1ms), immediately freeing up our Python/Flask HTTP threads.
*   **Simplified Operational Model**: Monitoring, backups, and scaling of Redis are already established in our production runbooks.
*   **Future WebSocket Support**: Redis's lightweight Pub/Sub and stream models are ideal for powering real-time WebSocket connections, aligning perfectly with our 2-quarter roadmap.

### Negative (Cons)
*   **Memory Footprint & Volatility**: Message state is stored in RAM. To prevent memory exhaustion under high traffic, we must enforce a strict stream-capping policy (e.g., using `MAXLEN ~ 100000` or `MINID` on `XADD`) and immediately offload processed history to PostgreSQL.
*   **No Long-term Message Retention**: Unlike Kafka, which persists data to disk indefinitely, Redis Streams is an ephemeral buffer. We cannot replay notifications from days ago unless we build a custom archiving mechanism into PostgreSQL.
*   **No Native Connectors**: We must write custom Python application logic to handle retries with exponential backoff and routing to Dead-Letter Queues (DLQs).

### Follow-up Action Items
1.  **Stream Capping**: Configure all producer `XADD` commands to use the approximate capping operator `~` (e.g., `XADD notification_stream MAXLEN ~ 50000 * ...`) to bound memory growth.
2.  **Worker Idempotency**: Implement a `processed_notifications` table in PostgreSQL. Workers will insert the unique stream Message ID (`timestamp-sequence`) inside a PostgreSQL transaction alongside the billing state update to guarantee exactly-once processing.
3.  **Retry & DLQ Logic**: Implement an async worker loop in Python that catches failures, schedules retries via Redis Sorted Sets (`ZSET`), and routes permanently failed messages to a `failed_notifications` PostgreSQL table for manual intervention.
4.  **Monitoring**: Add alerts on Redis RAM utilization and consumer group pending message counts (`XPENDING`).

---

## Alternatives Considered

### Apache Kafka (Rejected)
While Apache Kafka is the industry standard for high-throughput, persistent event streaming, we have rejected it for the following reasons:

1.  **Prohibitive Operational Complexity**: Operating a self-hosted Kafka cluster requires Zookeeper or KRaft coordination, careful JVM heap configuration, OS-level page cache tuning, partition assignment management, and broker failure recovery. With a 6-person team and no dedicated platform engineer, the operational burden would consume significant engineering cycles.
2.  **Financial & Learning Curve Barriers**: The team has no Kafka experience, meaning a steep learning curve and high risk of misconfiguration in production. Managed Kafka (such as Confluent Cloud) is too expensive for our modest budget.
3.  **Timeline Infraction**: Provisioning a high-availability Kafka cluster, implementing client wrappers in Python, and conducting load/failure testing would easily exceed 3-4 weeks, violating the 2-week setup constraint.
4.  **Inefficiency at Scale**: Kafka is designed for gigabytes-per-second streaming across large clusters. For our peak 5,000 req/s scale, Kafka's operational footprint is excessively heavy.
5.  **Redundancy of Exactly-Once Semantics (EOS)**: Kafka supports native transactional APIs, but this guarantees exactly-once processing only within Kafka-to-Kafka topologies. Since our notifications are ultimately dispatched to third-party HTTP endpoints (SendGrid, external webhooks) and our state is recorded in PostgreSQL, Kafka’s internal transactional mechanisms are redundant. We would still be forced to implement database-level idempotency checks in Python, nullifying Kafka's EOS benefit.
