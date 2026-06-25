# ADR-001: Selecting Redis Streams for the Notification Subsystem

- **Status**: Proposed
- **Date**: 2026-06-25
- **Deciders**: Engineering Team (6 members: 3 senior, 3 mid-level)
- **Context tags**: architecture, notification, messaging, async, billing, scale

## Context

### Product Scale and Current Metrics
Our SaaS project management platform currently services:
- **85,000 monthly active users (MAU)**
- **~2M tasks created per month**
- **Peak traffic of ~500 req/s** during business hours.

### Existing Architecture
Our current software and hardware stack consists of:
- **Backend**: Python/Flask monolith (~50k lines of code).
- **Database**: PostgreSQL (single primary instance, one read replica).
- **Infrastructure**: 4 web servers behind an Nginx load balancer hosted on AWS.
- **Cache**: Redis, currently used for session storage and rate limiting.
- **Notifications**: Handled synchronously inside the HTTP request cycle.

### The Problem
The current synchronous notification mechanism (sending emails and triggering webhooks immediately when tasks are updated, assigned, or completed) has introduced critical production issues:
1. **Request Timeouts**: Sending notifications blocks the user response. The average response latency has grown to 800ms, spiking to 8s during peak traffic.
2. **Silent Failures**: When third-party email providers or client webhook endpoints are down, notifications are silently dropped. There is no retry policy, dead-letter queue (DLQ), or error-tracking mechanism.
3. **Cascading Failures**: High latencies or outages from slow external webhook endpoints have twice exhausted the backend’s database connection pool, taking down unrelated platform features.
4. **Lack of Delivery Guarantees**: Core billing-critical events (e.g., "trial expired", "payment failed") require reliable delivery guarantees, which the current synchronous, non-transactional code path cannot support.

### Scaling Target and Future Requirements
The new notification subsystem must satisfy the following:
- **Decoupled Async Processing**: Move notification compilation and dispatch out of the HTTP request-response cycle.
- **Reliable Retries**: Support automatic retries with exponential backoff for failed deliveries.
- **Delivery Guarantees**: Guarantee at-least-once delivery for billing events, and exactly-once processing where feasible.
- **Real-Time Delivery**: Add real-time WebSocket push notifications within 2 quarters.
- **10x Scale Growth**: Handle 10x traffic growth without a complete architectural redesign (~5,000 peak req/s, 20M tasks/month).

### Constraints
- **Team Size & Capabilities**: 6 engineers (3 senior, 3 mid-level) with **no dedicated infrastructure/DevOps engineer** and **zero Apache Kafka experience**.
- **Time-to-Value**: Must not require more than **2 weeks of setup and migration work** before delivering production value.
- **Budget**: Modest. Fully managed options like Confluent Cloud are cost-prohibitive at our current scale and growth trajectory.
- **Existing Resources**: Redis is already provisioned, configured, and actively running in our production environment.

---

## Decision

We will use **Redis Streams** as the message broker for our asynchronous notification subsystem, combined with application-level consumer idempotency backed by PostgreSQL to handle billing-critical transactions.

> **Decision Statement**: We will use Redis Streams to decouple notifications and handle high-throughput async processing, and we will reject Apache Kafka due to its high operational complexity and resource footprint.

### Justification
For a 6-person team with a 2-week delivery window and zero Kafka experience, Redis Streams is the optimal choice. It provides a robust, built-in consumer group model and high-performance message streaming on top of our existing, already-paid-for Redis infrastructure. While Redis Streams does not support native broker-side transactional exactly-once semantics (EOS) for external API side-effects, we will achieve exactly-once processing (EOP) via Redis’s at-least-once delivery combined with application-level idempotency inside PostgreSQL. This avoids the severe operational overhead, steep learning curve, and infrastructure costs associated with Kafka.

---

## Consequences

Implementing Redis Streams introduces the following trade-offs and architectural commitments:

### Positive (Pros)
1. **Sub-Millisecond Latency and Ultra-High Throughput**: 
   Operating purely in-memory, Redis easily handles 10k–100k+ read/write operations per second on a single modest core. Under our 10x scale target of **5,000 req/s**, Redis Streams will operate with sub-millisecond overhead, leaving ample room for future growth.
2. **Zero New Infrastructure**: 
   Since Redis is already running in our production environment, we do not need to provision new AWS instances, establish new VPC networks, or write new terraform modules. This guarantees we can deploy to production and deliver value within the 2-week limit.
3. **Consumer Groups (`XGROUP` / `XREADGROUP`)**: 
   Redis Streams provides native, built-in consumer group support. We can horizontally scale lightweight consumer worker processes across our existing 4 web servers, distributing message processing with auto-balancing and tracking which worker has claimed which message.
4. **Resilience and Retries via Pending Entries List (PEL)**: 
   If a worker crashes mid-execution, the message is not lost; it remains in the consumer group’s Pending Entries List (PEL). We can use `XPENDING` and `XCLAIM` to detect stalled messages and safely retry them, ensuring **at-least-once delivery**.
5. **Synergy with Upcoming WebSocket Features**: 
   Redis is the industry-standard broker for scaling WebSockets (using its native Pub/Sub features or Streams). Using Redis for the notification engine creates a unified stack for the real-time push engine scheduled for Q2.
6. **Low Team Cognitive Load**: 
   The team is already comfortable with Redis. Transitioning to Redis Streams requires only learning a few commands (`XADD`, `XREADGROUP`, `XACK`), making it far safer than introducing a highly complex system like Kafka.

### Negative (Cons)
1. **Memory-Bound Durability (RAM Constraints)**: 
   Unlike Kafka, which persists all messages to disk indefinitely, Redis is strictly bound by system memory. Leaving notification logs in Redis forever will exhaust RAM and cause OOM failures. We must strictly enforce stream capping during writes (e.g., `XADD stream:notifications MAXLEN ~ 50000`) or periodically delete acknowledged entries, treating the stream as a transient buffer rather than an archival log.
2. **No Native Dead-Letter Queue (DLQ)**: 
   Redis Streams does not automate DLQ routing. If a notification repeatedly fails (e.g., a malformed email payload), we must write application-level logic to track retry counts (via `XPENDING` counter) and manually route the "poison" message to a separate stream (e.g., `stream:notifications:dlq`) after $N$ attempts.
3. **Manual Idempotency for Exactly-Once Semantics**: 
   Since Redis Streams does not natively coordinate transactions across our primary PostgreSQL database, we must explicitly implement consumer-side deduplication. Consumers must track processed message IDs within a PostgreSQL database transaction to guarantee exactly-once processing for billing.

---

## Alternatives Considered

### Apache Kafka (Rejected)
Apache Kafka is a distributed event streaming platform designed for high-volume, log-structured messaging. We evaluated Kafka but rejected it due to the following structural misalignments:

1. **Massive Operational Complexity**: 
   Kafka requires a highly complex management plane, relying on Apache ZooKeeper or KRaft metadata layers, multi-broker cluster coordination, and fine-tuned JVM performance settings. Running self-hosted Kafka with a 6-person team and no dedicated DevOps engineer is an extreme operational hazard that would drain product development bandwidth.
2. **Cost-Prohibitive**: 
   Due to our budget constraints, managed Kafka (e.g., Confluent Cloud or AWS MSK) is cost-prohibitive at our scale. Self-hosting a high-availability Kafka cluster requires a minimum of 3 brokers and 3 ZooKeeper/KRaft nodes, multiplying our AWS bill unnecessarily.
3. **Time-to-Value Violation**: 
   Provisioning, configuring, securing (TLS/SASL), monitoring, and integration-testing a production-ready Kafka environment would easily exceed our 2-week migration constraint.
4. **Overkill for Throughput**: 
   Kafka is optimized for multi-gigabyte-per-second streaming pipelines. Our 10x peak scale target is **5,000 messages/sec**, which is trivial for a single Redis instance and does not justify the massive footprint of Kafka.
5. **No Advantage for External Side-Effects**: 
   Kafka’s native exactly-once transactional API only functions within Kafka-to-Kafka streaming topologies. Because notifications involve external HTTP side-effects (such as SendGrid or client webhooks) that cannot participate in a Kafka-mediated two-phase commit, we would still have to implement application-level, consumer-side idempotency. Thus, Kafka offers no technical advantage over Redis Streams for our delivery guarantees.

---

## Technical Property Comparison Matrix

| Technical Property | Apache Kafka | Redis Streams (Our Choice) |
| :--- | :--- | :--- |
| **Throughput** | Millions of messages/sec (Overkill for our 5,000 req/s target). | 10,000 to 100,000+ messages/sec per core (Effortlessly scales past our 10x target). |
| **Operational Complexity** | **Very High** (Requires ZooKeeper/KRaft, multi-broker configuration, JVM tuning, partitions management). | **Minimal** (Leverages our existing Redis server, zero infrastructure overhead). |
| **Learning Curve** | **Steep** (No team experience, complex client configurations, partitioning strategies). | **Shallow** (Familiar Redis interface, basic stream commands, well-supported Python libraries). |
| **Message Retention** | **Infinite/Long-term** (Disk-backed, can act as a permanent source of truth). | **Transient/Short-term** (RAM-bound, must prune streams via `MAXLEN` to prevent OOM). |
| **Ordering Guarantees** | Guaranteed within a specific topic partition. | Guaranteed chronologically out-of-the-box for the entire stream. |
| **Consumer Groups** | Highly robust, built-in partition rebalancing. | Built-in via `XGROUP`/`XREADGROUP` (Fully supports horizontal scale-out). |
| **Exactly-Once Semantics (EOS)** | Internal EOS via transactional API (Does not extend to external webhooks/emails). | Achieved via at-least-once PEL retries combined with application-side PostgreSQL idempotency keys. |
| **Delivery Timeframe** | 4 to 6 weeks for staging, integration, security, and testing. | **< 1 week** for complete setup, testing, and production deployment. |
| **Financial Cost** | High (Managed services or multi-node EC2 hosting). | **Zero additional cost** (Runs on our existing, underutilized Redis instance). |

---

## High-Level Implementation Plan

To safely migrate to Redis Streams within 2 weeks, we will execute the following steps:

1. **Message Enqueueing**: 
   In the Flask HTTP request cycle, replace synchronous email/webhook dispatches with a fast non-blocking `XADD` call to a `stream:notifications` queue with a soft cap of 100,000 messages (`XADD stream:notifications MAXLEN ~ 100000 * notification_payload`).
2. **Horizontal Worker Pool**: 
   Deploy a worker pool (using a process manager like Supervisor or run as sidecars on our AWS instances) executing a Python consumption loop:
   ```python
   # Simplified Consumer Loop
   while True:
       messages = redis_client.xreadgroup(
           groupname="notification_group",
           consumername="worker_1",
           streams={"stream:notifications": ">"},
           count=10,
           block=2000
       )
       for stream, payload_list in messages:
           for msg_id, payload in payload_list:
               try:
                   process_notification(msg_id, payload)
                   redis_client.xack("stream:notifications", "notification_group", msg_id)
               except Exception:
                   # Error handler / local retry logic
                   pass
   ```
3. **Billing Exactly-Once Processing (EOP)**: 
   For billing-critical notifications:
   - Ensure the producer attaches a deterministic `idempotency_key` (e.g., `billing_payment_failed:invoice_92819`) to the message payload.
   - On the consumer side, wrapping the processing logic in a PostgreSQL database transaction:
     ```sql
     -- Attempt to insert the idempotency key to prevent double-processing
     INSERT INTO processed_notifications (idempotency_key) VALUES ('billing_payment_failed:invoice_92819');
     ```
   - If the insert succeeds, dispatch the email/webhook. If it fails with a unique constraint violation, acknowledge the message using `XACK` and skip processing, as it is a duplicate.
4. **Retry & Recovery Sweeper**: 
   Run a secondary background cron task every 5 minutes that calls `XPENDING stream:notifications notification_group`. For any message pending for more than 5 minutes:
   - If the delivery attempt is < 3, use `XCLAIM` to assign it to an active worker for retry.
   - If the delivery attempt has reached 3, log the failure and route it to `stream:notifications:dlq`, then call `XACK` on the original stream to prevent further loops.
