# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform currently handles critical notifications (email, webhooks) synchronously within the HTTP request cycle. This has led to request timeouts, silent failures on external service outages, and cascading failures due to connection pool exhaustion. Billing-critical notifications lack delivery guarantees.

**Key Requirements & Constraints:**
*   **Problem:** Request timeouts (avg 800ms, spikes to 8s), silent failures, cascading failures, no delivery guarantees (especially for billing-critical events).
*   **Scaling Target:** Decouple notifications (async processing), support retry with exponential backoff, guarantee at-least-once delivery for billing events, aim for exactly-once where feasible, support real-time WebSocket push notifications within 2 quarters, handle 10x traffic growth.
*   **Team:** 6 engineers (3 senior, 3 mid), no dedicated infrastructure engineer.
*   **Existing Infrastructure:** Redis is already in production for session management and rate limiting. No existing Kafka experience.
*   **Timeline:** Must deliver value within 2 weeks of setup/migration.
*   **Budget:** Modest; cannot afford managed Confluent Cloud at full scale.
*   **Criticality:** Exactly-once semantics are required for billing notifications.

## Decision
We choose **Redis Streams** for the notification subsystem.

This decision prioritizes speed of implementation, operational simplicity, and leverage of existing infrastructure knowledge given our team's size and current expertise. While Apache Kafka offers superior capabilities for extreme scale and complex stream processing, the operational overhead and learning curve for a team with no prior Kafka experience and limited infrastructure resources are too high for the immediate needs and constraints. Redis Streams can effectively address all immediate problems and meet scaling targets for the foreseeable future.

## Consequences

### Pros
*   **Leverages Existing Infrastructure & Expertise:** We already operate Redis in production, meaning the team is familiar with its deployment, monitoring, and basic operations. This significantly reduces the learning curve and operational burden.
*   **Fast Time to Value:** Redis Streams can be set up and integrated quickly, aligning with the "<2 weeks of setup/migration" constraint. Basic asynchronous processing with retry and delivery guarantees can be achieved rapidly.
*   **Addresses Immediate Problems:** Decoupling notifications, supporting retry mechanisms, and providing at-least-once delivery (with consumer groups and acknowledgments) are core features of Redis Streams, directly solving the current pain points.
*   **Cost-Effective:** Utilizing our existing Redis instance, or adding a modestly sized new one, will be significantly more budget-friendly than a new Kafka cluster (especially managed services).
*   **Suitable for Scaling Targets:** Redis Streams offer sufficient throughput for 10x traffic growth from our current 500 req/s peak, allowing us to manage millions of events per day efficiently.
*   **WebSocket Integration:** Redis Pub/Sub (and by extension Streams) is a natural fit for real-time WebSocket push notifications, simplifying the implementation of this future requirement.
*   **Exactly-Once Feasibility:** While not providing Kafka's native distributed transaction capabilities, Redis Streams allow for effective exactly-once processing for billing notifications by combining consumer group semantics with application-level idempotency (e.g., using a unique transaction ID and checking a deduplication store before processing).

### Cons
*   **Operational Scale Limits:** While adequate for 10x growth, Redis Streams may eventually reach a scaling ceiling for extremely high throughput (e.g., hundreds of millions or billions of messages per day across many partitions) compared to Kafka's design for petabyte-scale streaming data.
*   **Complex Stream Processing:** Redis Streams' capabilities for complex event stream processing (e.g., joins, aggregations across multiple streams over time windows) are less mature and feature-rich than Kafka Streams or ksqlDB.
*   **Durability and Retention:** While configurable, long-term historical message retention in Redis Streams (e.g., years of data) can be more resource-intensive and less optimized than in Kafka, which is designed for this use case.
*   **Exactly-Once Implementation Complexity:** Achieving robust exactly-once semantics for billing across external systems will require careful application-level design (idempotency, transaction coordination) rather than relying on a platform's built-in distributed transaction features.

## Alternatives Considered

### Apache Kafka
Apache Kafka was considered due to its industry-leading performance, durability, and robust features for distributed stream processing.

**Rejection Rationale:**
Despite its strengths, Kafka was rejected primarily due to our team's current constraints:
*   **High Operational Complexity:** Kafka requires significant operational expertise for deployment, tuning, and monitoring. This would place an undue burden on our small engineering team which lacks a dedicated infrastructure engineer and has no prior Kafka experience.
*   **Steep Learning Curve:** The learning curve for Kafka, including its concepts (topics, partitions, brokers, Zookeeper/Kraft, consumer groups, offsets), APIs, and best practices, is substantial. This directly conflicts with the "<2 weeks of setup/migration" constraint.
*   **Budgetary Constraints:** While open-source, managing Kafka at scale can be resource-intensive. Managed Kafka services (like Confluent Cloud) would likely exceed our modest budget for full-scale production.
*   **Time to Value:** The time required to set up a production-ready Kafka cluster, integrate it with our Python/Flask monolith, and train the team would significantly exceed the two-week timeline for delivering initial value, delaying critical fixes to our notification system.
*   **Overkill for Immediate Needs:** While Kafka can handle extreme scale, our immediate requirement (10x current traffic, which is still moderate compared to Kafka's full capability) can be met by a simpler solution. The advanced features of Kafka, such as sophisticated stream processing and global distributed transactions, are not immediate necessities and do not outweigh the operational overhead.
