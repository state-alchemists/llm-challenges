# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification subsystem, part of a Python/Flask monolith, handles emails and webhooks synchronously within the HTTP request cycle. This approach has led to significant problems:
1.  **Request timeouts**: Notifications block the main application, causing high latency (average 800ms, spikes to 8s).
2.  **Silent failures**: Notifications are dropped without retry or a dead-letter queue if external services are unavailable.
3.  **Cascading failures**: Slow external webhook endpoints have caused connection pool exhaustion, leading to broader system outages.
4.  **No delivery guarantees**: Critical billing notifications (e.g., "trial expired," "payment failed") lack guaranteed delivery, specifically requiring exactly-once semantics.

The team's goal is to decouple notifications for asynchronous processing, implement robust retry mechanisms with exponential backoff, ensure at-least-once delivery, and achieve exactly-once semantics for billing-critical events. The system must support 10x traffic growth and integrate real-time WebSocket push notifications within two quarters.

**Key Constraints:**
*   **Team Size**: 6 engineers (3 senior, 3 mid), with *no dedicated infrastructure engineer*.
*   **Existing Infrastructure**: Redis is already in production for session management and rate limiting.
*   **Kafka Experience**: No prior Kafka experience within the team.
*   **Timeline**: Must deliver value within 2 weeks of setup/migration.
*   **Budget**: Modest; cannot afford full-scale managed Kafka solutions like Confluent Cloud.
*   **Delivery Guarantees**: Exactly-once semantics for billing notifications is a critical requirement.

## Decision
We will adopt **Redis Streams** for the new asynchronous notification subsystem.

This decision is driven primarily by the critical operational constraints of our engineering team. While Apache Kafka offers a more comprehensive and robust solution for high-throughput, complex distributed streaming, its operational complexity and the team's lack of prior experience pose an unacceptably high risk and integration timeline given our current resources.

Redis Streams, on the other hand, leverages our existing Redis infrastructure and team knowledge. It provides the core messaging capabilities required to address the immediate problems:
*   **Asynchronous Processing**: Messages can be pushed to a stream and processed by dedicated workers, decoupling them from the HTTP request cycle.
*   **Reliability**: Consumer groups with explicit acknowledgment (`XACK`) and pending entries list (PEL) allow for reliable processing, retries, and handling of consumer failures, ensuring at-least-once delivery.
*   **Operational Simplicity**: As a native Redis data type, Redis Streams requires no new infrastructure to manage beyond our existing Redis instances. This significantly reduces the operational burden and learning curve for a team without a dedicated infrastructure engineer.
*   **Scalability**: Redis Streams can handle high throughput, and can scale horizontally with Redis Cluster if needed in the future, supporting our 10x traffic growth target without a fundamental re-architecture.
*   **Timeline**: Integration of Redis Streams into our existing Flask application for basic async notifications is achievable well within the 2-week timeframe.
*   **Exactly-Once Semantics**: While strictly "exactly-once" delivery is challenging in any distributed system without careful application-level design, Redis Streams' consumer group mechanisms provide a strong foundation for at-least-once delivery. For billing-critical notifications, application-level idempotency will be implemented in the notification processing workers to achieve effective exactly-once processing.

## Consequences

**Pros of Redis Streams:**
*   **Low Operational Overhead**: Leverages existing Redis instances and team operational knowledge, eliminating the need for new infrastructure management (e.g., Zookeeper, Kafka brokers).
*   **Fast Time to Value**: Easy to integrate with the existing Python/Flask application, allowing us to decouple notifications and achieve async processing quickly (within 2 weeks).
*   **Cost-Effective**: No immediate additional infrastructure costs, as it utilizes the existing Redis setup.
*   **Sufficient Feature Set**: Provides robust consumer groups, at-least-once delivery, message retention, and ordering guarantees within a stream, which are sufficient for our current and projected needs.
*   **Scalability**: Capable of handling significant throughput and scales horizontally with Redis Cluster.
*   **Real-time Capabilities**: Well-suited for future WebSocket push notification integration, as Redis is commonly used for real-time messaging.

**Cons of Redis Streams:**
*   **Less Mature Ecosystem**: Compared to Kafka, the ecosystem for advanced stream processing, monitoring, and connectors is less mature, though rapidly improving.
*   **Limited Long-Term Retention**: While configurable, Redis Streams are not designed for indefinite, petabyte-scale data retention like Kafka. This is acceptable for notification messages which are typically ephemeral after processing.
*   **Less Robust Transactional Guarantees**: Achieving strong transactional guarantees and global exactly-once semantics across multiple services is more complex than with Kafka's robust transactional API (though still requires careful application design in Kafka too). We will rely on application-level idempotency for critical billing events.
*   **Single-Threaded Nature of Redis**: While highly performant, Redis is single-threaded. Extremely high write throughput to a *single* stream could become a bottleneck on a single Redis instance, though this is unlikely for our projected notification volumes.

## Alternatives Considered

### Apache Kafka
**Reason for Rejection:**
Apache Kafka was considered due to its industry-leading capabilities for high-throughput, fault-tolerant distributed streaming and its strong support for complex data pipelines. It offers:
*   **Superior Scalability and Durability**: Designed for petabytes of data and extremely high message rates.
*   **Robust Ecosystem**: Mature tools, connectors, and stream processing frameworks (Kafka Streams, ksqlDB).
*   **Stronger Exactly-Once Semantics**: With idempotent producers, transactional consumers, and robust APIs, Kafka provides more comprehensive support for exactly-once processing guarantees across multiple stages.

However, Kafka was rejected due to several critical constraints:
*   **High Operational Complexity**: Kafka is a complex distributed system requiring significant expertise to set up, manage, monitor, and scale (Zookeeper/KRaft, brokers, partitions, replication). Our team *lacks a dedicated infrastructure engineer* and has *no prior Kafka experience*. This would necessitate a steep learning curve and divert valuable engineering resources from product development.
*   **Extended Setup/Migration Time**: Deploying and integrating Kafka from scratch, especially self-hosted, would far exceed our *2-week timeline* for delivering value.
*   **Budget Constraints**: While self-hosting is an option, the operational overhead (man-hours) is a significant cost. Managed services like Confluent Cloud are expensive and exceed our *modest budget* for full-scale adoption.
*   **Risk of Failure**: Introducing a complex, unfamiliar technology without dedicated expertise significantly increases the risk of deployment failures, prolonged outages, and development roadblocks.

While Kafka remains a powerful tool for large-scale, critical streaming platforms, it is not the right fit for our current team and project constraints.