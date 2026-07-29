# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

## Context

The existing notification module, integrated synchronously within our Python/Flask monolith, has become a significant bottleneck. With 85,000 monthly active users and ~2M tasks created per month, the synchronous notification sending leads to HTTP request timeouts (average 800ms, spikes to 8s), silent failures due to external service unavailability, and cascading failures that impact unrelated features. Crucially, there are no delivery guarantees, which is unacceptable for billing-critical notifications requiring at-least-once, and ideally exactly-once, processing.

Our scaling targets include decoupling notifications for asynchronous processing, implementing retry mechanisms with exponential backoff, ensuring at-least-once (and exactly-once for critical events) delivery, and enabling future real-time WebSocket push notifications. The system must also handle 10x traffic growth without major re-architecture.

Key constraints:
*   **Team Size & Expertise**: A 6-person engineering team with no dedicated infrastructure engineer and no prior Kafka experience.
*   **Existing Infrastructure**: We already operate Redis in production for session management and rate limiting.
*   **Time to Value**: Must deliver initial value within two weeks of setup/migration.
*   **Budget**: Modest, precluding costly managed services like Confluent Cloud.
*   **Guarantees**: Exactly-once semantics for billing notifications is a hard requirement.

## Decision

We will implement the new notification subsystem using **Redis Streams**.

This decision is driven primarily by the critical constraints of team expertise, operational overhead, and budget, while still meeting all functional requirements. Redis Streams provide a robust, message-queuing solution that leverages our existing Redis infrastructure and team familiarity, significantly reducing the learning curve and time to deployment compared to Apache Kafka.

Redis Streams offer:
*   **Asynchronous Processing**: Decouples notification sending from the HTTP request cycle.
*   **Consumer Groups**: Provides distributed consumption, allowing multiple workers to process messages in parallel, ensuring load balancing and fault tolerance. Messages are ordered within a stream partition (which is the stream itself in Redis) and delivered to consumers in a round-robin fashion within a group.
*   **At-Least-Once Delivery**: Achieved through consumer acknowledgments (`XACK`). Unacknowledged messages can be reclaimed and reprocessed by other consumers.
*   **Exactly-Once Semantics (Billing-Critical)**: Can be achieved by implementing idempotent consumers that store the last processed message ID in a durable data store (our existing PostgreSQL database) before committing the Redis Stream offset. This pattern ensures that even if a message is re-delivered, it is processed only once effectively.
*   **Configurable Message Retention**: `MAXLEN` allows us to manage stream size and retention based on our needs.
*   **Lower Operational Complexity**: As Redis is already in production, adding Streams functionality requires minimal new infrastructure or operational knowledge. The primary Redis instance can be horizontally scaled if needed.
*   **Fast Time to Value**: Leveraging existing infrastructure and skills aligns with the two-week setup/migration constraint.
*   **Scalability**: Redis Streams can handle the current peak load and scale for 10x traffic growth by adding more consumer instances and potentially sharding Redis if a single instance becomes a bottleneck in the distant future.

## Consequences

### Pros
*   **Reduced Operational Overhead**: Minimal learning curve and no new infrastructure required for a dedicated message broker, significantly easing management for the small team.
*   **Faster Development & Deployment**: Leveraging existing Redis knowledge accelerates implementation.
*   **Cost-Effective**: No additional infrastructure costs or expensive managed service fees initially.
*   **Strong Foundation for Real-time Notifications**: Redis's pub/sub capabilities are an excellent fit for future WebSocket push notifications.
*   **Decoupling**: Eliminates request timeouts and cascading failures caused by synchronous notification processing.
*   **Reliable Delivery**: Provides mechanisms for retry, dead-letter queuing (via a separate Redis Stream for failed messages), and exactly-once processing for critical notifications.

### Cons
*   **Limited Ecosystem & Tooling (compared to Kafka)**: Redis Streams have a less mature ecosystem for complex stream processing, monitoring, and integration with third-party tools compared to Kafka. This might require more custom development for advanced features.
*   **Less Scalable for Extreme Throughput**: While sufficient for our 10x growth target, Kafka is fundamentally designed for higher throughput and larger-scale data ingestion scenarios that Redis Streams might struggle with at the extreme end without significant sharding and careful management.
*   **Less Opinionated on Exactly-Once**: Achieving exactly-once semantics requires more application-level logic (e.g., tracking message IDs in PostgreSQL) compared to Kafka's transactional APIs (though these often require a more complex Kafka setup).
*   **Single Point of Failure (Potentially)**: While Redis can be highly available, a single Redis cluster managing both cache and streams could become a single point of failure or resource contention if not properly monitored and scaled. This risk is mitigated by careful resource allocation and monitoring.

## Alternatives Considered

### Apache Kafka

Apache Kafka was considered due to its industry-standard position for high-throughput, fault-tolerant distributed streaming platforms.

**Reasons for Rejection**:
*   **High Operational Complexity**: Setting up and maintaining a Kafka cluster (including ZooKeeper or Kraft mode) requires significant specialized knowledge and operational effort. This is a major hurdle for our 6-person team with no dedicated infrastructure engineer and no prior Kafka experience.
*   **Steep Learning Curve**: The team would need substantial time to learn Kafka's concepts, APIs, and operational best practices, directly conflicting with the "two weeks to value" constraint.
*   **Budget Constraints**: Self-hosting Kafka requires significant compute resources and expertise. Using managed services like Confluent Cloud would exceed our modest budget at scale, especially given the required features for high availability and exactly-once semantics.
*   **Overkill for Initial Needs**: While Kafka excels at massive scale, its advanced features and complexity are overkill for our immediate problem of decoupling notifications and achieving basic delivery guarantees. Redis Streams offer a more appropriate balance of features and operational simplicity for our current scale and team capabilities.
*   **Time to Value**: The time required for setup, learning, and integration would far exceed the mandated two-week window for delivering value.

While Kafka offers superior capabilities for very large-scale, enterprise-grade data streaming, its operational burden and learning curve make it an impractical choice for our current team and constraints.