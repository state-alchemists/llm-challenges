# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, causing HTTP request timeouts (up to 8s spikes), silent failures during downstream outages, and cascading failures that exhaust connection pools. 

We must decouple notifications from the request cycle to support asynchronous processing, retries with exponential backoff, and specific delivery guarantees for billing-critical events.

**Key Constraints:**
- **Team:** 6 engineers; no dedicated infra/DevOps specialist.
- **Infrastructure:** AWS, existing Redis deployment for sessions/rate-limiting.
- **Knowledge:** Zero internal experience with Apache Kafka.
- **Timeline:** Maximum 2 weeks for initial setup and value delivery.
- **Scale:** Peak 500 req/s, targeting 10x growth (5,000 req/s).
- **Requirements:** Exactly-once semantics for billing; at-least-once for others.

## Decision
We will use **Redis Streams** as the backbone for the notification subsystem.

### Justification
Given the current team composition and infrastructure, Redis Streams provides the optimal balance of required functionality and operational simplicity.

1. **Operational Complexity:** We already operate Redis in production. Introducing Kafka would require deploying and managing a new cluster (or paying for managed Confluent Cloud, which exceeds the current budget). Kafka's operational overhead (Zookeeper/KRaft, JVM tuning, partition management) is too high for a 6-person team without an infra engineer.
2. **Throughput & Scale:** Redis Streams can easily handle the current 500 req/s and the 10x growth target (5,000 req/s) on modest hardware. The bottleneck will be the external API providers (Email/Webhooks), not the stream throughput.
3. **Consumer Groups:** Redis Streams supports Consumer Groups, enabling the same horizontal scaling and message distribution patterns as Kafka.
4. **Delivery Guarantees:** 
    - **At-least-once:** Achieved via explicit acknowledgments (`XACK`).
    - **Exactly-once (Billing):** Since Redis is a key-value store, we can implement idempotency by storing the `message_id` or a business-level `transaction_id` in a Redis set/hash during processing, ensuring billing notifications are not processed twice.
5. **Time-to-Value:** Integration can begin immediately using existing infrastructure, meeting the 2-week setup constraint.

## Consequences

### Pros
- **Zero New Infrastructure:** Leverages existing Redis deployment; no new binaries or clusters to manage.
- **Low Latency:** Extremely high performance for produce/consume operations.
- **Fast Iteration:** Minimal learning curve for the team; rapid implementation of the retry logic and DLQs.
- **Future-Proofing:** Well-suited for the planned WebSocket push notifications (can easily integrate with Redis Pub/Sub or Streams).

### Cons
- **Memory Bound:** Unlike Kafka, which persists to disk, Redis Streams consume RAM. We must implement a strict `MAXLEN` (capping stream size) and a retention policy to prevent OOM errors.
- **Persistence Trade-off:** While RDB/AOF provides persistence, it is not as durable as Kafka's distributed commit log in the event of total cluster failure. (Acceptable risk given the nature of notifications).

## Alternatives Considered

### Apache Kafka
Rejected for the following reasons:
- **Operational Overhead:** Too complex for a small team to manage reliably without dedicated infra expertise.
- **Cost:** Managed services (Confluent) are outside the current budget; self-hosting is an operational liability.
- **Over-Engineering:** Kafka's strengths (massive throughput, long-term retention, complex stream processing) are not required for a 5,000 req/s notification system.
- **Timeline:** The learning curve and setup time would likely exceed the 2-week window for delivering initial value.
