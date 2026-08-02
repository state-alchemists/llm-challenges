# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context

### Background & System Baseline
We operate a B2B SaaS project management platform. The current operational envelope and production infrastructure consist of:
- **Workload Metrics**: 85,000 Monthly Active Users (MAU), generating approximately 2,000,000 task creations and updates per month.
- **Traffic Profile**: A business-hours peak of approximately 500 requests per second (req/s).
- **Current Architecture**:
  - A monolith backend implemented in Python/Flask (~50,000 lines of code).
  - PostgreSQL as the primary database, utilizing a single primary node and one read replica.
  - Deployment across 4 web servers hosted on AWS, sitting behind an Nginx load balancer.
  - Redis used in production for session storage and rate limiting.
  - **Notifications**: Synchronously dispatched within the HTTP request cycle when tasks are created, updated, or completed (sending emails and webhook payloads).

### Core Architectural Problems
Under current traffic, the synchronous execution model has introduced severe stability and performance degradation:
1. **Request Latency and Timeouts**: Sending notifications blocking the main Flask HTTP request cycle leads to average response latencies of 800ms, spiking up to 8,000ms (8 seconds) during business-hours peaks.
2. **Silent Delivery Failures**: In the event of network partition, email SMTP provider downtime, or slow webhook endpoints, notifications are dropped silently. There is no automated retry mechanism, backoff policy, or Dead-Letter Queue (DLQ).
3. **Cascading Failure/Resource Exhaustion**: Two major outages occurred this year due to slow external client webhook endpoints. The synchronous HTTP workers blocked waiting on socket I/O, resulting in connection pool exhaustion on the Flask monolith, taking down unrelated platform features.
4. **Lack of Delivery Guarantees**: Critically sensitive notifications (such as subscription/billing notifications like "trial expired" or "payment failed") have no reliability or delivery guarantees.

### Scaling Target & Future Requirements
To support business scaling over the next 10x growth phase (~20,000,000 tasks per month, ~5,000 peak req/s) and future feature sets, the notification subsystem must satisfy:
- **Asynchronous Decoupling**: Offload all email, webhook, and push notifications to an asynchronous processing layer out of the synchronous HTTP request-response cycle.
- **Robust Error Handling**: Provide automatic message redelivery and error handling, including exponential backoff with jitter and routing to a Dead-Letter Queue (DLQ) after exhaustive failures.
- **Delivery Guarantees**: Maintain at-least-once delivery for general notifications, and exactly-once processing guarantees for billing-critical events.
- **Real-Time Push Capabilities**: Seamlessly support the integration of real-time WebSocket push notifications to client browsers, scheduled for rollout within two quarters.
- **10x Scale Envelope**: Absorb and process up to 5,000 req/s under peak load without requiring a subsequent infrastructure re-architecture.

### Resource & Project Constraints
1. **Team Size & Infrastructure Capacity**: The engineering team consists of only 6 individuals (3 senior, 3 mid-level) with no dedicated DevOps, site reliability, or infrastructure engineers.
2. **Existing Technologies**: Redis is already fully operational in production for caching/session state.
3. **Skill Gaps**: The team has zero operational or development experience with Apache Kafka.
4. **Time-to-Value Constraint**: The migration and setup of the new async subsystem must be complete and delivering production value in under 2 weeks.
5. **Budgetary Limits**: Modest budget constraints rule out high-cost, fully managed streaming services like Confluent Cloud at our projected 10x scale.


## Decision

We will use **Redis Streams** as the messaging backbone for the asynchronous notification subsystem. 

### Rationale & Justification

Redis Streams is the optimal choice for our specific organizational capabilities, time constraints, and technical requirements. The decision is justified across the following key technical dimensions:

#### 1. Operational Simplicity vs. Team Constraints
With an engineering team of 6 people and no dedicated infrastructure engineer, minimizing "operational tax" is paramount. 
- **Redis Streams**: Since Redis is already provisioned, secured, and monitored in our production environment, introducing Redis Streams has a **marginal operational cost of zero**. No new infrastructure components, security groups, cluster topologies, or monitoring stacks are required.
- **Kafka**: Implementing Apache Kafka would require provisioning and managing a complex distributed cluster (relying on Zookeeper or KRaft). Given the team's zero Kafka experience, setting up, tuning, securing, and monitoring Kafka in production is highly unlikely to be completed within the 2-week timeframe. 

#### 2. Technical Capabilities vs. 10x Scale Target
Our 10x scaling target requires supporting up to 5,000 peak req/s. 
- **Throughput**: A single-node Redis instance easily handles tens of thousands of write/read operations per second with sub-millisecond latency. Our peak target of 5,000 req/s is well within the capabilities of our existing Redis deployment.
- **Consumer Groups**: Redis Streams natively supports consumer groups through `XGROUP` and consumer reading via `XREADGROUP`. This matches Kafka's consumer group model, enabling us to distribute notification processing across multiple parallel worker processes (e.g., Celery, RQ, or custom lightweight Python consumers).
- **Delivery Guarantees & Fault Tolerance**: Redis Streams tracks message delivery status natively. A consumer reads messages, and if it crashes before processing, the message remains in the Pending Entries List (PEL). A separate orchestrator or active consumer can inspect the PEL via `XPENDING`, claim dead messages using `XCLAIM` / `XAUTOCLAIM`, and execute retries. Once processed, the consumer issues an `XACK`, ensuring robust **at-least-once delivery** guarantees.

#### 3. Exactly-Once Semantics (EOS) for Billing
- It is a common misconception that message brokers alone can provide end-to-end exactly-once delivery across external APIs (like SMTP or webhooks). If an external email provider successfully processes a request but the connection drops before returning a response, the broker must retry, leading to duplicate delivery.
- Therefore, exactly-once processing must be enforced at the consumer level using **at-least-once delivery combined with consumer-side idempotency**.
- We will generate a unique `notification_id` (UUIDv4) at the producer (Flask monolith) and include it in the message payload. Consumers will track processed IDs using either a unique constraint in PostgreSQL or a fast, TTL-bounded key-value lookup in our existing Redis cache. Redis is uniquely suited to perform this deduplication step with minimal latency, resolving the billing notification constraint cleanly.

#### 4. Real-Time WebSockets Integration
The scaling target mandates real-time WebSocket push notifications within two quarters. Redis is the industry-standard backplane for WebSocket servers (e.g., scaling Flask-SocketIO or FastAPI WebSockets). We can easily use Redis Pub/Sub alongside Redis Streams to broadcast events to WebSocket worker nodes, creating a unified, elegant real-time push architecture without introducing new dependencies.

#### 5. Financial Prudence
Self-hosting Kafka at our 10x scale introduces substantial AWS compute, storage, and networking costs, while managed solutions like Confluent Cloud are cost-prohibitive. Redis Streams operates inside our existing Redis footprint, requiring only minor memory allocations, which aligns perfectly with our modest budget.


## Consequences

### Positive (Pros)
- **Zero Infrastructure Overhead**: Reuses our existing production Redis cluster, avoiding extra AWS bills, monitoring overhead, and provisioning delays.
- **Immediate Time-to-Value**: The team can implement the entire producer/consumer architecture using standard Python libraries (like `redis-py` or lightweight wrappers) well within the 2-week deadline.
- **Guaranteed FIFO Ordering**: Redis Streams guarantees message ordering within a single stream key, ensuring that sequential notification events (e.g., "Task Assigned" then "Task Completed") are processed in the correct order.
- **Horizontal Scalability**: Consumer groups allow us to scale the number of background notification workers horizontally on AWS ECS or EC2 as traffic increases.
- **Low Latency**: Message write and read latencies in Redis are sub-millisecond, far outperforming disk-heavy broker alternatives at our scale.

### Negative (Cons)
- **In-Memory Limitations**: Redis is entirely in-memory. If consumer workers crash and messages pile up, memory usage will grow. To mitigate this risk, we must enforce streaming retention boundaries using `MAXLEN ~` or `XTRIM` to prune processed messages, and actively monitor Redis memory usage via Alertmanager/CloudWatch.
- **Lack of Deep Message Retention / Archival**: Unlike Kafka, which can store TBs of historical stream data on disk for weeks, Redis Streams are not designed as historical archives. We must persist durable notification history and delivery logs directly into our PostgreSQL read replica after successful consumption if auditing is required.
- **Manual Backoff and DLQ Management**: While Redis Streams tracks pending messages, constructing exponential backoff retries and Dead-Letter Queue (DLQ) routing must be handled in our application code (or via a lightweight Python framework like Celery/Huey).

### Follow-Ups and Mitigation Plan
1. **Idempotency Layer**: Implement a unique `notification_id` deduplication check in PostgreSQL / Redis for all consumer workers processing billing events.
2. **Stream Trimming**: Configure all producers to call `XADD` with the `MAXLEN ~ 100000` option to cap memory consumption per stream.
3. **Monitoring and Alerting**: Configure AWS CloudWatch / Datadog alerts on Redis memory utilization (`used_memory`) to prevent Out-Of-Memory (OOM) failures under heavy backlog spikes.
4. **DLQ Implementation**: Establish a dedicated Redis Stream (e.g., `notifications:dlq`) where messages are routed after 5 failed processing attempts.


## Alternatives Considered

### Option 1: Apache Kafka

Apache Kafka is a highly distributed, disk-backed commit log designed for high-throughput event streaming. While powerful, it was rejected for the following critical reasons:

- **Prohibitive Operational Complexity**: Operating a high-availability Kafka cluster requires extensive expertise in partition management, replication factors, JVM garbage collection, and broker clustering. With a 6-person team and no dedicated DevOps engineer, self-hosting Kafka would create a massive operational bottleneck, diverting engineering hours away from core product features.
- **Violating the 2-Week Constraint**: Installing Kafka, establishing proper monitoring/alerting, updating CI/CD pipelines, and writing client consumer code with complex libraries (like `confluent-kafka` or `aiokafka`) would comfortably exceed the 2-week setup window.
- **Financial Unviability**: Managed Kafka alternatives (such as AWS MSK or Confluent Cloud) would introduce high fixed monthly costs that conflict with the team's modest budget.
- **Over-Engineering**: Kafka is designed for processing millions of events per second across hundreds of microservices. At our peak scaling target of 5,000 req/s on a single Python monolith, Kafka is an excessive solution that introduces unnecessary architectural complexity.
