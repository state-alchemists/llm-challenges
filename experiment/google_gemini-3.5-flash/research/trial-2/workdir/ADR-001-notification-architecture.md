# ADR 001 — Selection of Redis Streams for Decoupled Notification Architecture

- **Status**: Accepted
- **Date**: 2026-07-29
- **Deciders**: Zaruba (Software Architect)
- **Context tags**: architecture, notification-subsystem, redis-streams, kafka, python-flask

## Context

We run a SaaS project management platform that is experiencing performance and reliability issues due to its synchronous notification system (`system_context.md:4-15`). 

### Key Scale Metrics:
- 85,000 monthly active users (`system_context.md:5`)
- ~2M tasks created per month (`system_context.md:6`)
- Peak workload of ~500 requests/second during business hours (`system_context.md:7`)

### Core Problems with Synchronous Model:
1. **Request Timeouts**: Sending emails and webhooks synchronously blocks the HTTP request cycle. Average response latency is 800ms, spiking to 8s during peak hours (`system_context.md:19-20`).
2. **Silent Failures**: Network glitches or downstream service outages (e.g., email providers or client webhook endpoints) cause notifications to be silently dropped without retry mechanisms or Dead-Letter Queues (DLQs) (`system_context.md:21-22`).
3. **Cascading Failures**: Connection pool exhaustion caused by slow external webhook endpoints has already caused two major platform incidents this year, taking down unrelated features (`system_context.md:23-25`).
4. **No Delivery Guarantees**: Critical billing notifications (e.g., "trial expired", "payment failed") have no delivery guarantees, risking customer churn or lost revenue (`system_context.md:25`).

### Scaling Target:
- Decouple notification delivery from the HTTP request cycle using asynchronous queueing (`system_context.md:29`).
- Support exponential backoff and retries for failed deliveries (`system_context.md:30`).
- Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible (`system_context.md:31`).
- Support real-time WebSocket push notifications within 2 quarters (`system_context.md:32`).
- Gracefully handle 10x traffic growth (target peak of 5,000 requests/second) without requiring architectural rewrites (`system_context.md:33`).

### Constraints:
- **Small Team**: 6 engineers (3 senior, 3 mid) with no dedicated infrastructure engineer to manage complex systems (`system_context.md:36`).
- **Time-to-Value**: The solution must be up, running, and delivering value in under 2 weeks (`system_context.md:39`).
- **Existing Tech Stack**: Python/Flask monolith backend, PostgreSQL database, and a Redis instance currently used for session storage and rate limiting (`system_context.md:10-14`).
- **Budget**: Modest; cannot support the high operational costs of self-hosted message brokers or expensive managed options like Confluent Cloud (`system_context.md:40`).
- **Experience**: The engineering team has zero Kafka experience (`system_context.md:38`).
- **Semantics**: Exactly-once processing must be maintained for critical billing events (`system_context.md:41`).

---

## Decision

> We will use **Redis Streams** as the message broker to decouple the notification subsystem from the HTTP request cycle.

### Justification:
Redis Streams provides all the technical primitives required (consumer groups, acknowledgements, high throughput, and ordering guarantees) to solve our delivery and timeout problems. By utilizing our existing Redis deployment, we bypass the need to provision, secure, and monitor new infrastructure.

To meet the requirement for exactly-once semantics for billing notifications (`system_context.md:41`), we will implement an **At-Least-Once transport mechanism** (via Redis Streams consumer groups, pending entry tracking, and explicit worker acknowledgements) combined with **idempotent consumer processing** at the business/database layer. The consumers will leverage PostgreSQL transactions and unique database constraints to guarantee exactly-once processing. This eliminates the need for Kafka’s complex transactional API.

---

## Consequences

### Positive (Pros):
- **Immediate Time-to-Value**: Because Redis is already running in production (`system_context.md:37`), we avoid infrastructure provisioning, network security adjustments, and learning curves. The team can deliver a working prototype and production-ready worker in less than 5 days, easily satisfying the 2-week constraint (`system_context.md:39`).
- **Low Operational Overhead**: Since we do not have a dedicated infrastructure engineer (`system_context.md:36`), keeping our infrastructure footprint identical is highly advantageous. We use existing monitoring, backup strategies, and security rules.
- **Outstanding Throughput**: A single Redis instance easily handles over 100,000 operations per second. Scaling 10x to 5,000 requests/second (`system_context.md:33`) represents a small fraction of Redis's capabilities and will run comfortably on a single modest Redis node.
- **Robust Consumer Groups**: Redis Streams supports Consumer Groups (`XGROUP` / `XREADGROUP`). It maintains a Pending Entries List (PEL) for each consumer, which keeps track of unacknowledged messages. If a worker fails, another worker can inspect the PEL and claim ownership (`XCLAIM`) of the stale messages, guaranteeing at-least-once delivery and preventing silent notification drops (`system_context.md:21-22`).
- **WebSocket Integration Readiness**: Having Redis as our broker enables us to seamlessly build the real-time WebSocket push notifications planned for next quarter (`system_context.md:32`) using Redis Pub/Sub or Streams as the backend transport layer.
- **Zero Budget Impact**: We avoid additional managed service licensing or infrastructure costs, keeping our expenditures minimal (`system_context.md:40`).

### Negative (Cons):
- **In-Memory Limitations**: Unlike Kafka, which persists all messages to disk indefinitely, Redis is an in-memory database. Storing millions of historical notification payloads in memory would lead to out-of-memory (OOM) crashes.
  * *Mitigation*: We will configure our producers to prune streams automatically during additions (e.g., `XADD stream MAXLEN ~ 10000`) and enforce strict consumer-side message trimming once messages are successfully processed and acknowledged.
- **No Native Long-Term Message Replay**: If we need to re-run historical notification jobs from weeks ago, Redis Streams cannot replay them since historical messages are pruned to save memory.
  * *Mitigation*: We will log the state of all sent notifications in our persistent PostgreSQL database. If an audit or replay is required, a simple administrative script can query PostgreSQL and re-enqueue the events.
- **No Distributed Exactly-Once Transactions**: Redis Streams does not provide out-of-the-box distributed transaction boundaries spanning across Redis and PostgreSQL.
  * *Mitigation*: Exactly-once semantics are achieved at the database layer. Every notification event will carry a unique UUID (event ID). Consumer workers will write to a `processed_notifications` table in PostgreSQL within a database transaction. A unique constraint on the event ID will prevent duplicate processing.

---

## Alternatives Considered

### 1. Apache Kafka
Kafka was evaluated and rejected for the following reasons:
- **High Operational Complexity**: Kafka requires either ZooKeeper or a KRaft controller cluster, JVM tuning, disk provisioning, partition management, and specialised network configurations. Running Kafka reliably requires substantial infrastructure experience, which our 6-person team lacks (`system_context.md:36`).
- **Prohibitive Cost**: Managed services (e.g., Confluent Cloud) would solve the operational burden but violate our modest budget constraint (`system_context.md:40`). Self-hosting Kafka would require significant EC2 costs and devour valuable engineering hours.
- **Steep Learning Curve**: With zero Kafka experience on the team (`system_context.md:38`), training, testing, and deployment would take several weeks or months, completely missing our 2-week time-to-value constraint (`system_context.md:39`).
- **Overkill for Our Current Scale**: While Kafka is excellent for high-volume event streaming (hundreds of thousands of events/sec), our 10x target scale of 5,000 requests/second (`system_context.md:33`) is easily and cheaply accommodated by Redis.

*What would make us choose Kafka instead?*
We would choose Kafka if our scaling targets exceeded 100,000 requests/second, if we required permanent stream retention for event sourcing/replayability, or if we had a dedicated DevOps/SRE team with deep Kafka expertise.
