
# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing synchronous notification system in our Python/Flask monolith is causing significant issues including request timeouts, silent failures, cascading system failures due to slow external dependencies, and a lack of delivery guarantees for critical billing events. We need to transition to an asynchronous, reliable notification architecture that can scale to 10x current traffic, support at-least-once delivery for all events, and achieve exactly-once delivery for billing-critical events. Future plans include real-time WebSocket push notifications.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We currently use Redis for session storage and rate limiting. There is no existing team experience with Apache Kafka. The solution must be implemented with minimal setup/migration time (under 2 weeks to deliver value) and within a modest budget, precluding expensive fully-managed solutions like Confluent Cloud for initial scale.

## Decision
We choose **Redis Streams** for the notification subsystem.

## Consequences
### Pros
*   **Leverages existing infrastructure & expertise**: We already operate Redis in production, reducing the operational overhead and learning curve for the team. This directly addresses the constraint of having no dedicated infrastructure engineer and a short setup/migration timeline.
*   **Lower operational complexity**: Managing a Redis instance is significantly simpler than a Kafka cluster, especially for a small team without Kafka expertise. This aligns with the modest budget constraint by avoiding the need for expensive managed Kafka services or dedicated ops staff.
*   **Fast time to value**: Integration with Redis Streams is typically straightforward in Python applications, allowing us to quickly decouple notification sending and implement retry mechanisms within the 2-week target.
*   **Built-in consumer groups**: Redis Streams provide consumer groups, which enable multiple consumers to process messages from a stream concurrently, ensuring load balancing and fault tolerance – a key requirement for reliable asynchronous processing.
*   **At-least-once delivery**: With consumer acknowledgments, Redis Streams can guarantee at-least-once delivery for all messages, addressing the silent failures and delivery guarantee problems.
*   **Exactly-once semantics (feasible)**: While not as natively robust as Kafka's transactional APIs, exactly-once processing can be achieved with Redis Streams through careful consumer design (e.g., using idempotent consumers and tracking processed message IDs in a durable store), which is a crucial requirement for billing notifications.
*   **Suitable for future WebSocket needs**: Redis's pub/sub capabilities (though distinct from Streams) are well-suited for real-time WebSocket communication, offering a cohesive ecosystem for future feature development.

### Cons
*   **Scalability for extreme throughput**: While Redis Streams can handle significant throughput (thousands to tens of thousands of messages/sec per instance), Kafka is designed for orders of magnitude higher scale (millions of messages/sec). If our traffic growth far exceeds the 10x target in the very long term, a migration to Kafka might eventually be necessary, incurring a larger re-architecture effort.
*   **Message retention**: Redis Streams' memory usage grows with message retention. While it supports trimming, long-term, high-volume message archiving or replay requires careful management or offloading to a more persistent store. Kafka is inherently designed for long-term, high-volume data retention.
*   **Transactionality for exactly-once**: Achieving robust exactly-once semantics requires more application-level logic (idempotency) compared to Kafka's native support for transactions spanning multiple partitions or topics. This adds complexity to critical consumers.

## Alternatives Considered
### Apache Kafka
Kafka was considered due to its industry-leading capabilities for high-throughput, distributed messaging, and strong delivery guarantees. However, it was rejected for the following reasons:
*   **High operational complexity**: Operating a Kafka cluster is notoriously complex, requiring deep expertise in distributed systems, ZooKeeper/Kraft, topic management, and monitoring. This directly conflicts with our team's constraint of having no dedicated infrastructure engineer and no prior Kafka experience. The 2-week setup/migration timeline would be impossible to meet for a new Kafka deployment.
*   **Budget constraints**: While open-source Kafka is free, running it reliably at scale often necessitates expensive managed services (like Confluent Cloud) or significant internal operational investment, which is beyond our current modest budget.
*   **Overkill for initial scale**: While the scaling target is 10x, Kafka's extreme throughput capabilities are likely over-provisioned for our immediate needs, introducing unnecessary complexity and cost.
*   **Steeper learning curve**: The team's lack of Kafka experience would lead to a substantial learning curve, delaying value delivery and increasing the risk of operational errors.
*   **Transactionality**: While Kafka offers robust exactly-once semantics via transactional producers and consumers, the complexity of setting this up and integrating it into a new ecosystem outweighed the benefits given our team's constraints and the availability of a feasible alternative in Redis Streams.
