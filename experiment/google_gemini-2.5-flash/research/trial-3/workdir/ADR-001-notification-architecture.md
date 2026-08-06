# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification module, integrated synchronously into the HTTP request cycle of our Python/Flask monolith, is causing significant operational issues. With 85,000 monthly active users and ~2M tasks created per month, peak loads of ~500 req/s lead to request timeouts (average 800ms, spikes to 8s) and silent failures for critical notifications due to a lack of retry mechanisms or dead-letter queues. This synchronous approach has also led to cascading failures, exhausting connection pools when external webhook endpoints are slow. Critically, billing-related notifications lack guaranteed delivery, which is unacceptable.

We need to decouple notifications for asynchronous processing, implement retry with exponential backoff, and guarantee at-least-once delivery for billing events, with exactly-once delivery where feasible. The new system must support 10x traffic growth and integrate real-time WebSocket push notifications within two quarters.

Our constraints include a small engineering team of six (no dedicated infrastructure engineer), a modest budget precluding expensive managed solutions like Confluent Cloud at scale, and a tight timeline of two weeks for initial value delivery. We already utilize Redis in production for session management and rate limiting, but our team has no prior Kafka experience.

## Decision
We choose **Redis Streams** as the foundation for our new notification subsystem.

While Apache Kafka offers robust features for large-scale distributed streaming, Redis Streams provides a more pragmatic and immediately beneficial solution given our specific constraints, particularly the team's size, lack of Kafka expertise, existing Redis infrastructure, and tight delivery timeline. Redis Streams offers fundamental streaming capabilities with lower operational overhead, leveraging a technology our team is already familiar with. This minimizes the learning curve and deployment complexity, allowing us to deliver value quickly.

Redis Streams supports consumer groups, enabling multiple consumers to process messages from a stream in parallel, distributing the workload effectively. It provides at-least-once delivery semantics by default, which is critical for billing notifications, and can be extended for idempotent processing to achieve exactly-once semantics at the application level. Its append-only log structure ensures message ordering per stream, and configurable message retention allows us to manage data efficiently.

## Consequences

### Pros
*   **Lower Operational Complexity:** As we already operate Redis, integrating Redis Streams introduces minimal new operational overhead. Our team is familiar with Redis monitoring, backup, and scaling patterns, significantly reducing the learning curve for the notification subsystem. This directly addresses the constraint of having no dedicated infrastructure engineer.
*   **Faster Time to Value:** With existing Redis knowledge, we can implement and deploy Redis Streams much faster than a completely new technology like Kafka. This aligns with the "not require more than 2 weeks of setup/migration work before delivering value" constraint.
*   **Cost-Effective:** Utilizing our existing Redis infrastructure or scaling it incrementally is more budget-friendly than deploying and managing a full Kafka cluster, especially given our "modest budget."
*   **Real-time Capabilities:** Redis is inherently fast and well-suited for real-time scenarios, making it a strong candidate for supporting future WebSocket push notifications within the two-quarter target.
*   **Message Ordering:** Redis Streams maintain the order of messages within a single stream, which is crucial for event sequencing in many notification scenarios.
*   **Consumer Groups:** Built-in consumer group support allows for distributed and fault-tolerant message processing, addressing the need for parallel processing and workload distribution.

### Cons
*   **Throughput Limitations Compared to Kafka:** While Redis Streams offers good throughput for its use cases, it may not match the raw throughput and horizontal scalability of a finely tuned, multi-broker Kafka cluster for extremely high-volume, global-scale streaming. This might require careful partitioning and sharding of Redis instances for the anticipated 10x growth, though it is manageable within our scaling target.
*   **Exactly-Once Semantics:** Achieving true end-to-end exactly-once semantics requires careful application-level idempotency, as Redis Streams primarily offers at-least-once delivery. Kafka's transaction capabilities can simplify this for complex scenarios, but for our specific billing notifications, application-level handling is feasible.
*   **Message Retention Management:** Redis Streams retention is typically time-based or size-based. For very long-term message archival or replaying historical events over extended periods, Kafka's design with durable, distributed logs is more inherently suited. We will need to manage retention policies actively to prevent excessive memory usage.
*   **Ecosystem Maturity:** The Kafka ecosystem (tools, connectors, integrations) is more mature and extensive than that of Redis Streams. We may need to develop custom integrations for certain notification types or external systems.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-standard capabilities in distributed streaming, high throughput, and robust delivery guarantees.

*   **Rejected due to operational complexity:** Kafka introduces a significant operational overhead. Running a Kafka cluster (even a small one) requires expertise in Zookeeper (or KRaft), broker management, partitioning, replication, and monitoring. Our team of six engineers, with no dedicated infrastructure specialist and no prior Kafka experience, would face a steep learning curve and substantial time investment to set up and maintain a production-ready Kafka environment. This directly conflicts with the "no dedicated infrastructure engineer" and "2 weeks setup/migration" constraints.
*   **Rejected due to budget constraints for managed services:** While self-hosting is an option, it exacerbates the operational complexity. Managed Kafka services like Confluent Cloud, which would alleviate some operational burden, are currently outside our "modest budget" at full scale.
*   **Overkill for initial problem:** While Kafka is excellent for very high throughput and complex streaming analytics, our immediate need is to decouple notifications, add retry, and guarantee delivery for critical messages. Redis Streams can meet these requirements with significantly less friction. Although Kafka offers stronger guarantees for exactly-once semantics through its transaction API, the complexity of implementing and operating this with an inexperienced team outweighs the benefits for our initial use case.
*   **Learning curve:** The absence of "Kafka experience on the team today" and the "modest budget" for training or external consultation make Kafka a higher-risk, longer-term investment than Redis Streams for this immediate problem.

Ultimately, while Kafka remains a powerful platform for future, more complex streaming needs, it is not the right fit for our current team, budget, and urgent timeline for solving the notification problem.
