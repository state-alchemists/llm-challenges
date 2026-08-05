# ADR-001: Notification Subsystem Architecture

## Status
Accepted

## Context
We run a SaaS project management platform serving 85,000 monthly active users (MAU) with ~2 million tasks created per month and a peak load of ~500 requests per second (req/s) during business hours.

The current architecture comprises a Python/Flask monolith (~50k LOC) running on 4 AWS-hosted web servers behind an nginx load balancer. It relies on a single PostgreSQL primary database with one read replica, and uses Redis for session storage and rate limiting.

Currently, the notifications module (which sends emails and webhooks for task events) executes synchronously within the HTTP request cycle. This has introduced critical production issues:
1. **Request Timeouts**: Sending notifications blocks HTTP threads, averaging 800ms of latency and spiking up to 8 seconds during peak hours.
2. **Silent Failures**: If third-party email providers or client webhook endpoints are down, notifications are silently dropped with no retry or Dead-Letter Queue (DLQ).
3. **Cascading Failures**: Unchecked latency in consumer-defined webhook endpoints has twice caused database connection pool exhaustion, leading to platform-wide downtime.
4. **No Delivery Guarantees**: Highly critical billing events (e.g., "trial expired", "payment failed") have no transactional delivery guarantees.

### Scaling Target
- Decouple the notification pipeline from the synchronous HTTP request cycle (asynchronous processing).
- Provide message retry with exponential backoff.
- Guarantee at-least-once delivery for general notifications, and strictly maintain exactly-once semantics (EOS) for critical billing notifications.
- Enable support for real-time WebSocket push notifications within 2 quarters.
- Scale to handle 10x traffic growth (peak ~5,000 req/s) without a complete system re-architecture.

### Constraints
- **Team Size**: Only 6 developers (3 senior, 3 mid-level) with zero dedicated infrastructure/DevOps engineers.
- **Expertise**: The team has no production experience operating or developing for Apache Kafka.
- **Timeline**: The system must deliver production value within 2 weeks of setup/migration.
- **Budget**: Modest budget; managed Kafka solutions like Confluent Cloud are cost-prohibitive.
- **Infrastructure**: We already successfully run Redis in production for sessions and rate limiting.

---

## Decision
We will use **Redis Streams** as the primary messaging backbone for the notification subsystem.

### Justification
Redis Streams perfectly aligns with our engineering constraints, timeline, and throughput targets while satisfying all functional delivery requirements:

1. **Operational Simplicity & Team Velocity**: We already run and monitor Redis in production. Reusing Redis Streams eliminates the risk and overhead of deploying, configuring, and monitoring new infrastructure. A 6-person team can deliver value in days (well within the 2-week limit), whereas setting up a production-ready Kafka cluster from scratch without prior experience would consume the entire timeline.
2. **Sufficient and Efficient Throughput**: At a 10x scaling target of 5,000 req/s, the corresponding notification event volume is estimated at 1,000–3,000 events/s. Redis Streams easily processes over 50,000 write operations/s per node with sub-millisecond latencies under low CPU/memory footprint, making Kafka's multi-million event scale unnecessary.
3. **Native Consumer Group Support**: Using Redis consumer groups (`XGROUP`, `XREADGROUP`), multiple worker processes can load-balance notification handling, scale horizontally, and track message progress.
4. **Reliable At-Least-Once Delivery**: Redis Streams implements a Pending Entries List (PEL) and explicit acknowledgements (`XACK`). If a notification worker crashes mid-execution, its unacknowledged messages remain in the PEL and can be claimed by active workers using `XPENDING` and `XAUTOCLAIM`, preventing message loss.
5. **Exactly-Once Semantics (EOS) for Billing Events**:
   - Notifications inherently integrate with external third-party services (e.g., SendGrid, Mailgun, external webhooks) which do not support distributed two-phase commits (2PC) or transactional boundaries. Consequently, Kafka's native transactional EOS *cannot* prevent double-delivery at the network boundary (e.g., if a worker crashes right after hitting SendGrid but before committing the offset).
   - Therefore, exactly-once semantics must be enforced at the consumer boundary via **idempotency keys**.
   - We will achieve EOS by generating a unique `notification_id` at the producer level and using Redis atomically as an idempotency lock (`SET <notification_id> processing EX 300 NX`) before invoking any external APIs.

---

## Consequences
### Pros
- **Immediate Time-to-Value**: Local development and production deployment can be configured and launched within days.
- **Near-Zero Cost**: No new software licensing or heavy managed service fees; we leverage our existing AWS Redis infrastructure.
- **Low Cognitive Overhead**: The team can focus on writing notification retry logic and WebSocket endpoints instead of debugging partition rebalancing, JVM tuning, or KRaft quorums.
- **Natural Path to WebSockets**: We can use our existing Redis infrastructure to power the upcoming real-time WebSocket push engine (leveraging Redis Pub/Sub or lightweight Streams) without adding another component.

### Cons
- **In-Memory Retention Risk**: Redis Stores its data structures in RAM. Unacknowledged streams can cause memory exhaustion if consumers fail. 
  *Mitigation*: We will use capped streams via `XADD` with `MAXLEN ~20,000` (or `MINID`) to prune processed messages.
- **Payload Overhead**: Storing large, deep notification payloads in RAM is inefficient.
  *Mitigation*: We will store only lightweight event metadata (e.g., `{"event_id": "123", "type": "task_updated", "tenant_id": "abc"}`) in the Stream, fetching the full body dynamically from our PostgreSQL read replica inside the worker.
- **Manual Offset Management**: Redis Streams does not automatically rebalance consumer partition ownership on worker join/leave events.
  *Mitigation*: Our worker processes will run a background thread or a periodic cron task executing `XAUTOCLAIM` to discover and process stale, unacknowledged messages.

---

## Alternatives Considered

### Apache Kafka
We rejected Apache Kafka for the following reasons:
- **Excessive Operational Complexity**: Kafka requires significant overhead to self-host (managing brokers, disk space, IOPS, replica lag, ZooKeeper/KRaft consensus, and OS/JVM parameters). With no dedicated infrastructure engineer, this would place an unacceptable operational burden on a 6-person team.
- **Time-to-Value Violation**: Acquiring Kafka expertise, establishing a deployment pipeline, writing custom Python wrappers (e.g., `confluent-kafka` or `aiokafka`), and verifying failover behavior would take far longer than our 2-week budget.
- **Prohibitive Cost**: Self-hosting Kafka requires a multi-node cluster for high availability, driving up AWS EC2/EBS bills. Managed alternatives like Confluent Cloud are cost-prohibitive given our modest budget.
- **Mismatched Capabilities**: Kafka is optimized for massive, high-throughput log ingestion and long-term disk persistence. Our notifications are transient and ephemeral—once delivered or retried, they have no long-term analytical value inside the message queue.
- **No Boundary Advantage for EOS**: Kafka's exactly-once transactions do not extend to external HTTP-based integrations (emails, webhooks). Since consumer-side idempotency is required regardless, Kafka provides no architectural advantage over Redis Streams for this constraint.
