# ADR-001: Notification Subsystem Architecture Decision

## Status
Proposed

## Context
The current notification module, part of a Python/Flask monolith, handles sending emails and webhooks synchronously within the HTTP request cycle. This approach has led to significant problems:
- **Request timeouts**: Average latency is 800ms, with spikes up to 8 seconds during peak hours, directly impacting user experience.
- **Silent failures**: Notifications are silently dropped if external services (email providers, webhook endpoints) are down, without retry mechanisms or dead-letter queues.
- **Cascading failures**: Slow external webhook endpoints have caused connection pool exhaustion, leading to outages in unrelated parts of the system.
- **No delivery guarantees**: Critical billing notifications (e.g., "trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

The system currently serves 85,000 monthly active users, generating approximately 2 million tasks per month, with peak traffic around 500 requests per second.

**Scaling Targets:**
- Decouple notification processing from the HTTP request cycle for asynchronous handling.
- Implement robust retry mechanisms with exponential backoff.
- Guarantee at-least-once delivery for all notifications, and strive for exactly-once semantics for billing-critical events.
- Support real-time WebSocket push notifications within two quarters.
- Architect for 10x traffic growth without requiring another complete re-architecture.

**Constraints:**
- **Team Size & Expertise**: A small engineering team of 6 (3 senior, 3 mid-level) with no dedicated infrastructure engineer. The team has existing familiarity with Redis for caching and session management, but no experience with Apache Kafka.
- **Timeline**: The initial setup and migration must deliver value within 2 weeks.
- **Budget**: Modest, precluding immediate adoption of expensive fully-managed Kafka services like Confluent Cloud at full scale.
- **Existing Infrastructure**: Redis is already deployed and in use for other purposes.

## Decision
We choose **Redis Streams** for the notification subsystem.

This decision prioritizes leveraging existing infrastructure and team expertise to achieve rapid value delivery and maintainable operational overhead, given the current team size and budget constraints. While Apache Kafka offers a more robust solution for large-scale, high-throughput, and complex distributed transaction scenarios, its adoption would introduce significant operational complexity and a steep learning curve for our team, violating the timeline and budget constraints.

Redis Streams provides a durable, ordered, and append-only log within the familiar Redis ecosystem. It supports consumer groups, which will allow for parallel processing of notifications and acknowledgement of messages, addressing the silent failures and decoupling requirements. Its integration with existing Redis instances minimizes infrastructure changes and operational overhead.

For billing-critical notifications requiring exactly-once semantics, we will implement idempotent consumers. While Redis Streams itself provides at-least-once delivery, combining this with application-level idempotency ensures that even if a message is processed multiple times, the external effect (e.g., sending an email) occurs only once. This pattern is well-understood and achievable within Redis Streams' capabilities.

## Consequences

### Pros
- **Lower Operational Complexity**: Leverages the existing Redis infrastructure, reducing the need to introduce and manage a completely new distributed system. The team's familiarity with Redis significantly lowers the learning curve for operations, monitoring, and troubleshooting.
- **Faster Time to Value**: The initial setup and integration are expected to be within the 2-week timeline, allowing the team to quickly address the critical notification problems.
- **Cost-Effective**: Utilizes existing Redis instances, avoiding the high costs associated with new managed services or the significant engineering effort of self-hosting a complex system like Kafka.
- **Good Throughput & Ordering**: Redis Streams offers good performance for the current and projected 10x traffic growth, and guarantees insertion order within a stream, which is sufficient for notification sequencing.
- **Consumer Groups**: Built-in support for consumer groups allows for distributed, fault-tolerant, and parallel processing of notification events, providing scalability and reliability.
- **Message Retention**: Configurable message retention allows for replaying events if needed for debugging or recovery.
- **Future-Proofing for WebSockets**: Redis Pub/Sub, part of the same Redis ecosystem, is a natural fit for future real-time WebSocket push notifications, simplifying the overall architecture for this next feature.

### Cons
- **Limited True Exactly-Once Semantics**: While "effectively once" can be achieved with idempotent consumers, Redis Streams does not offer the same robust, transaction-level exactly-once guarantees across producers, brokers, and consumers that Kafka provides through its transaction API. This requires careful application-level design and testing for critical billing events.
- **Scalability Ceiling (Eventual)**: While sufficient for 10x growth, Redis Streams might eventually hit a scalability ceiling for extremely high-throughput, petabyte-scale data streaming scenarios that Kafka is specifically designed for. However, this is not an immediate concern.
- **Persistence Model**: Redis Streams stores data in memory (though persistent via AOF/RDB). Very long-term, high-volume message retention could lead to increased memory usage compared to Kafka's disk-based storage model.
- **Fewer Advanced Features**: Lacks some of the more advanced stream processing capabilities, ecosystem tools, and enterprise-grade features available with Kafka (e.g., Kafka Connect, KSQL, dedicated stream processing frameworks).

## Alternatives Considered

### Apache Kafka
**Reason for Rejection**:
Apache Kafka is a highly performant, scalable, and durable distributed streaming platform, offering superior capabilities for high-throughput data ingestion, stream processing, and robust exactly-once semantics through its transaction API. It is designed for handling petabytes of data and integrating with a vast ecosystem of tools.

However, it was rejected primarily due to the **operational complexity and the current constraints of our engineering team**:
- **Steep Learning Curve**: None of our 6 engineers (3 senior, 3 mid-level) have Kafka experience. Introducing Kafka would require a significant investment in training, which would extend beyond the 2-week "value delivery" timeline.
- **High Operational Overhead**: Self-managing a Kafka cluster (including ZooKeeper or Kraft, brokers, monitoring, and scaling) requires dedicated infrastructure expertise, which our team lacks. While managed services exist, they are often expensive, exceeding our modest budget, especially at scale (e.g., Confluent Cloud).
- **Setup Time**: Deploying and configuring a production-ready Kafka cluster, even with a managed service, would likely exceed the stipulated 2-week setup/migration timeline, hindering our ability to quickly resolve the immediate notification issues.
- **Resource Intensive**: Kafka clusters can be resource-intensive in terms of CPU, memory, and disk I/O, requiring careful provisioning and management.

While Kafka's technical merits for large-scale event streaming and its stronger built-in exactly-once guarantees are compelling, the practical constraints of our team's size, expertise, budget, and aggressive timeline make it an unsuitable choice for the immediate problem. Adopting Kafka would introduce too much friction and risk, diverting valuable engineering resources from product development to infrastructure management. If the system's needs evolve beyond Redis Streams' capabilities and the team grows with dedicated infrastructure expertise, Kafka could be reconsidered in the future.
