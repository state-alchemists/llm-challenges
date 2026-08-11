# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform currently handles critical notifications (emails, webhooks for task updates, assignments, completions) synchronously within the HTTP request cycle. This approach has led to significant problems:

1.  **Request timeouts and high latency:** Synchronous notification sending blocks the HTTP response, causing average latencies of 800ms and spikes up to 8 seconds during peak hours.
2.  **Silent failures:** If an external notification provider (e.g., email service, webhook endpoint) is unavailable, notifications are silently dropped with no retry mechanism or dead-letter queuing.
3.  **Cascading failures:** Slow external webhook endpoints have caused connection pool exhaustion, leading to outages in unrelated parts of the system.
4.  **Lack of delivery guarantees:** Billing-critical notifications (e.g., "trial expired," "payment failed") currently have no guaranteed delivery, which is unacceptable for business operations.

The system needs to evolve to support 85,000 monthly active users and ~2M tasks created per month, with a peak of ~500 requests/second, and must scale to 10x traffic growth. Key requirements include decoupling notifications from the request cycle for asynchronous processing, implementing retry mechanisms with exponential backoff, guaranteeing at-least-once delivery for billing events (and exactly-once where feasible), and supporting real-time WebSocket push notifications within two quarters.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We currently use Python/Flask, PostgreSQL, and Redis (for session storage and rate limiting) on AWS. There is no existing team experience with Apache Kafka. The solution must provide initial value within 2 weeks of setup/migration, operate within a modest budget (ruling out full-scale managed Kafka solutions), and critically, maintain exactly-once semantics for billing notifications.

## Decision
We propose adopting **Redis Streams** for our notification subsystem.

This decision is primarily driven by the immediate operational complexity and experience constraints of our engineering team, combined with the need for rapid deployment and cost-effectiveness. While Apache Kafka offers superior capabilities for large-scale, enterprise-grade message queuing, its operational overhead and the team's lack of experience present a significant barrier to entry that outweighs its technical advantages for our current stage.

Redis Streams offers a robust, log-centric data structure with built-in features that address our immediate needs: durable messaging, consumer groups for scalable processing, and efficient message retention. Leveraging our existing Redis infrastructure simplifies deployment and reduces the learning curve significantly. Although true exactly-once semantics require careful client-side implementation (e.g., using idempotent consumers and tracking processed message IDs), this is deemed manageable given our team's existing Redis familiarity and the architectural simplicity gained.

## Consequences

### Pros of Redis Streams:
*   **Low Operational Complexity:** As we already run Redis in production, integrating Redis Streams introduces minimal new operational overhead. This is critical for a small team without a dedicated infrastructure engineer.
*   **Fast Time to Value:** Leveraging existing infrastructure and team familiarity allows for quick setup and migration, meeting the <2 weeks to value constraint.
*   **Cost-Effective:** Utilizing existing Redis instances or adding new Redis nodes is significantly more budget-friendly than deploying and managing a Kafka cluster or using expensive managed Kafka services.
*   **Good Performance:** Redis is an in-memory data store, offering high throughput and low latency, sufficient for our current and projected 10x scaling targets.
*   **Ordered Messages:** Messages within a single stream are strictly ordered, which is crucial for maintaining event sequence.
*   **Consumer Groups:** Redis Streams natively support consumer groups, enabling distributed processing and load balancing of notifications across multiple worker instances.
*   **Message Retention:** Configurable stream length (`MAXLEN`) allows us to manage memory usage while retaining messages for retries and historical analysis.
*   **At-least-once Delivery:** Guaranteed by consumer groups, and idempotent client-side processing can achieve effective exactly-once semantics for critical billing events.
*   **Real-time Capabilities:** Redis Pub/Sub, in conjunction with Streams, provides an excellent foundation for future real-time WebSocket push notifications.

### Cons of Redis Streams:
*   **Exactly-once Semantics (Client-side):** While achievable, true exactly-once delivery for billing events requires more careful design and implementation on the consumer side (e.g., managing consumer state and idempotency tokens) compared to Kafka's native transactional guarantees.
*   **Scalability vs. Kafka:** While Redis Streams can scale well, a single Redis instance has limits compared to a multi-broker Kafka cluster designed for petabytes of data and extreme throughput. Scaling Redis Streams for very high throughput might eventually require sharding or a cluster setup, adding complexity.
*   **Lack of Native Stream Processing:** Redis Streams do not offer the rich ecosystem of stream processing (like Kafka Streams, KSQL DB) that Kafka does. Complex event processing or transformations would require external application logic.
*   **Disk Persistence:** Redis Streams typically rely on Append Only File (AOF) or RDB snapshots for persistence. While durable, it's not designed for the same long-term, high-volume disk-backed retention as Kafka.

## Alternatives Considered

### Apache Kafka

Apache Kafka was considered due to its industry-leading capabilities as a distributed streaming platform, offering high throughput, fault tolerance, and strong delivery guarantees, including native support for exactly-once semantics via transactions.

**Reasons for Rejection:**
*   **High Operational Complexity:** Operating a Kafka cluster (even a small one) requires significant expertise in distributed systems, monitoring, and troubleshooting. Given our team of 6 engineers with no dedicated infrastructure engineer and no prior Kafka experience, this presents an unacceptably high learning curve and operational burden.
*   **Slow Time to Value:** The initial setup, configuration, and integration of Kafka would likely exceed our <2 weeks constraint, delaying critical value delivery.
*   **Budget Constraints:** While self-hosting is an option, the operational costs (engineering time, monitoring tools) would be substantial. Full-scale managed Kafka solutions like Confluent Cloud are currently out of our modest budget.
*   **Overkill for Immediate Needs:** For our current scale and immediate requirements, the full power and complexity of Kafka are not strictly necessary, especially when simpler alternatives can meet critical needs more quickly.
*   **Client Library Maturity/Complexity:** While Python Kafka clients exist, integrating them effectively with transactional semantics adds another layer of complexity for a team new to Kafka.

In summary, while Kafka is a powerful solution, its high barrier to entry in terms of operational complexity, learning curve, and cost makes it unsuitable for our team and constraints at this juncture. Redis Streams offers a more pragmatic, incremental approach that leverages existing expertise and infrastructure to solve the immediate problem efficiently.