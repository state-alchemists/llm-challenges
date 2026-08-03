# ADR-001: Notification Subsystem Architecture Decision

**Status**: Proposed

**Context**
The current notification module for our SaaS project management platform handles emails and webhooks synchronously within the HTTP request cycle. This has led to request timeouts, silent failures, cascading failures, and a lack of delivery guarantees, particularly for billing-critical notifications which require exactly-once semantics. We need to decouple notifications for asynchronous processing, support retry mechanisms, guarantee at-least-once (and where feasible, exactly-once) delivery, and support future real-time WebSocket push notifications, all while handling 10x traffic growth.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We already use Redis in production for session storage and rate limiting but have no Kafka experience. The solution must be deployable within two weeks of setup/migration to deliver value, and our budget is modest, precluding expensive managed Kafka solutions at scale. Exactly-once semantics for billing notifications is a hard requirement.

**Decision**
We have decided to implement the notification subsystem using **Redis Streams**. This decision is primarily driven by the team's existing familiarity with Redis, the modest budget constraints, and the shorter operational learning curve compared to Kafka. While Kafka offers robust features for large-scale, high-throughput scenarios, Redis Streams provides a more lightweight, yet capable, solution that aligns better with our immediate team and budget constraints while still addressing the critical functional requirements. The existing Redis infrastructure reduces setup time and complexity, allowing the team to deliver value faster.

**Consequences**
*   **Pros:**
    *   **Reduced Operational Complexity:** Leveraging an existing Redis instance simplifies deployment and monitoring. The team already has operational experience with Redis, reducing the learning curve.
    *   **Faster Time to Value:** Minimal setup and migration work due to existing infrastructure and Redis's simpler operational model. This aligns with the 2-week deployment target.
    *   **Cost-Effective:** Avoids the significant infrastructure costs and operational overhead associated with a new Kafka cluster, especially given the modest budget and lack of dedicated infra engineers.
    *   **Sufficient Throughput and Scalability:** Redis Streams can handle our current peak of ~500 req/s and scale to 10x traffic growth, particularly with horizontal scaling of Redis instances if needed.
    *   **At-Least-Once Delivery:** Consumer groups and explicit acknowledgment support at-least-once delivery for all notifications.
    *   **Ordering Guarantees:** Redis Streams inherently provides strict message ordering within a stream.
    *   **Consumer Groups:** Redis Streams' consumer groups provide distributed message processing, allowing multiple consumers to process a stream concurrently without duplicate processing, ensuring scalability for notification workers.
    *   **Message Retention:** Configurable stream retention policies allow us to keep messages for replay or auditing.
    *   **Exactly-Once Semantics (via Idempotency):** While Redis Streams does not offer native exactly-once *processing* guarantees, it provides strong at-least-once delivery. For billing-critical notifications, we will implement exactly-once semantics at the application level through idempotent processing, leveraging unique message IDs or transaction IDs within the notification payload.
    *   **Real-time Capabilities:** Redis Pub/Sub (complementary to Streams) is well-suited for the future WebSocket push notification requirement.

*   **Cons:**
    *   **Lower Throughput Ceiling (compared to Kafka):** While sufficient for 10x growth, Redis Streams may eventually hit a lower throughput ceiling than a highly optimized Kafka cluster for extreme scale (e.g., 100x+ growth or millions of events/second). However, this is a distant concern given our current scale.
    *   **Manual Idempotency for Exactly-Once:** Achieving true exactly-once *processing* requires more application-level logic (idempotency keys) compared to some Kafka setups that offer stronger transactionality guarantees. This adds development complexity for critical paths.
    *   **Fewer Ecosystem Integrations:** Kafka has a richer ecosystem of connectors and stream processing frameworks (e.g., Kafka Connect, KSQL) that Redis Streams lacks. This might mean more custom development for data integration in the future.
    *   **No Native Dead Letter Queue (DLQ):** Redis Streams does not have a built-in DLQ mechanism. Failed messages will require application-level handling (e.g., re-publishing to a separate "dead-letter" stream or logging to an error sink for manual inspection/reprocessing).

**Alternatives Considered**

**Apache Kafka** was considered and rejected for the following reasons:
*   **High Operational Complexity for Small Team:** Kafka introduces significant operational overhead. A small team of 6 engineers with no dedicated infrastructure specialist and no prior Kafka experience would struggle with the initial setup, configuration, monitoring, and maintenance of a Kafka cluster. This violates the "modest budget" and "fast time to value" constraints.
*   **Steeper Learning Curve:** The team's complete lack of Kafka experience would necessitate a significant learning period, impacting the project timeline and the 2-week setup/migration goal.
*   **Budget Constraints:** While self-hosting Kafka is an option, it requires substantial engineering effort and resources. Managed Kafka solutions like Confluent Cloud, which would reduce operational burden, are currently out of budget at full scale.
*   **Overkill for Current Scale:** While Kafka is designed for extremely high throughput and large-scale data pipelines, our current and projected 10x traffic (~5000 req/s peak) is well within Redis Streams' capabilities for this specific notification use case.
*   **Exactly-Once Semantics:** While Kafka offers stronger transactional guarantees which can simplify exactly-once *processing*, the operational burden outweighs this benefit for our team. We determined that application-level idempotency with Redis Streams is a more pragmatic approach given our team's profile.
*   **Message Retention:** Kafka's long-term message retention capabilities are superior, but Redis Streams' configurable retention is sufficient for our immediate needs, primarily for short-term retry and auditing.

The operational overhead and learning curve of Kafka for a small team with no prior experience were the primary deciding factors against its adoption at this stage.