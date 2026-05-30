---
Title: ADR-001 Notification Subsystem Architecture
Status: Proposed
---

# Notification Subsystem Architecture Decision

## Context

The current notification module, responsible for sending emails and webhooks upon task updates, is integrated synchronously within the HTTP request cycle of our Python/Flask monolith. This has led to critical issues: request timeouts (average 800ms, spikes to 8s), silent failures with no retry or dead-letter queue, and cascading failures due to slow external endpoints. Billing-critical notifications lack delivery guarantees.

We need to decouple notifications for asynchronous processing, implement retry with exponential backoff, ensure at-least-once delivery for billing events (and exactly-once where feasible), support 10x traffic growth, and enable future real-time WebSocket push notifications within two quarters.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We currently use Redis for session management and rate limiting. There is no existing Kafka experience within the team. The solution must be implemented and deliver value within two weeks, adhere to a modest budget (precluding managed Confluent Cloud at full scale), and guarantee exactly-once semantics for billing notifications.

## Decision

We have decided to adopt **Redis Streams** for our notification subsystem.

This decision is driven by the immediate need to address critical performance and reliability issues with minimal operational overhead and a rapid deployment timeline. Redis Streams provides the necessary message queuing capabilities, including ordering guarantees, consumer groups, and message retention, within an ecosystem the team is already familiar with. Its operational simplicity compared to Kafka is a crucial factor, aligning with our small team size and lack of dedicated infrastructure expertise.

## Consequences

### Pros

*   **Leverages existing infrastructure and expertise**: We already operate Redis in production, reducing the learning curve and operational burden for the team. This also aligns with the "no Kafka experience" constraint and the short setup time.
*   **Rapid implementation**: Integrating Redis Streams is expected to be significantly faster than deploying and configuring a new Kafka cluster, allowing us to deliver value within the two-week constraint.
*   **Reduced operational complexity**: Redis Streams is much simpler to manage, monitor, and scale than Kafka, which is vital for a team without a dedicated infrastructure engineer.
*   **Strong delivery guarantees**: Redis Streams, when combined with consumer groups and explicit `XACK` (acknowledgment) commands, provides robust at-least-once delivery semantics. Application-level idempotency can then achieve exactly-once processing for billing-critical events.
*   **Scalability**: Redis Streams can handle our projected 10x traffic growth (up to 5000 req/s) for message ingestion and processing effectively, especially with horizontal scaling of Redis instances if necessary.
*   **Real-time capabilities**: The stream model is well-suited for future WebSocket push notifications, as consumers can easily read and forward messages in real-time.

### Cons

*   **Lower extreme throughput than Kafka**: While sufficient for our 10x projected growth, Redis Streams may not match Kafka's ability to handle extremely high-volume data ingestion (millions of messages per second) over the very long term or for large-scale data lake integrations.
*   **Limited long-term message retention**: While configurable, Redis is typically not designed for indefinite message retention or as a primary data store for historical event logs, unlike Kafka. This might require an external archival strategy for auditing or analytics if strict long-term retention becomes a future requirement.
*   **Fewer ecosystem tools**: Kafka has a vast ecosystem of connectors, stream processing frameworks (e.g., Kafka Streams, Flink), and monitoring tools. Redis Streams has a growing ecosystem but is not as mature or comprehensive.

## Alternatives Considered

### Apache Kafka

Kafka was considered for its industry-leading throughput, robust ecosystem, and strong guarantees for fault tolerance and message delivery.

*   **Rejected due to operational complexity**: The primary reason for rejection is the significant operational overhead associated with deploying, managing, and scaling Kafka. This includes managing ZooKeeper (or Kraft mode), understanding partitioning, replication, and broker configurations. Our team lacks Kafka experience and a dedicated infrastructure engineer, making it a high-risk choice given the rapid setup timeline.
*   **Rejected due to budget constraints**: Managed Kafka services like Confluent Cloud, which would mitigate some operational burden, are outside our modest budget at full scale. Self-managing Kafka would incur substantial engineering time and expertise costs.
*   **Setup/migration time**: Introducing Kafka would almost certainly exceed the two-week setup/migration constraint, as the team would need to learn, deploy, and integrate a completely new distributed system.
*   **Learning curve**: The steep learning curve for Kafka would divert significant engineering resources, delaying the delivery of value.

While Kafka offers superior capabilities for large-scale, enterprise-grade streaming architectures, its total cost of ownership (TCO) in terms of operational complexity, learning curve, and budget makes it unsuitable for our current team and project constraints.
