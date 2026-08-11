# ADR-001: Notification Subsystem Architecture Decision

## Title
Notification Subsystem Architecture Decision: Apache Kafka vs. Redis Streams

## Status
Proposed

## Context
Our SaaS project management platform currently handles notifications (emails, webhooks for task updates) synchronously within the HTTP request cycle of our Python/Flask monolith. This approach has led to severe performance and reliability issues:

*   **Request timeouts and high latency:** Blocking I/O for sending notifications causes average response times of 800ms, with spikes up to 8 seconds during peak usage (~500 req/s).
*   **Silent failures:** Notifications are dropped without retry or dead-letter queuing if external services (email providers, webhook endpoints) are unavailable.
*   **Cascading failures:** Incidents of slow webhook endpoints exhausting connection pools, leading to outages of unrelated features.
*   **Lack of delivery guarantees:** Critical notifications (e.g., billing events like "trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

To address these issues and support future growth (10x traffic increase, real-time WebSocket push notifications within two quarters), we need to decouple notification processing from the main application logic. The new subsystem must:

*   Process notifications asynchronously.
*   Implement retry mechanisms with exponential backoff.
*   Guarantee at-least-once delivery for billing events, with exactly-once delivery as a goal where feasible.
*   Be scalable to handle significant traffic growth.

**Constraints:**
*   **Team:** 6 engineers (3 senior, 3 mid), with *no dedicated infrastructure engineer*.
*   **Existing Infrastructure:** We already utilize Redis for session management and rate limiting.
*   **Kafka Experience:** The team has *no prior experience* with Apache Kafka.
*   **Time to Value:** The solution must be implemented and delivering value within 2 weeks of setup/migration work.
*   **Budget:** Modest, precluding expensive managed Kafka solutions (e.g., Confluent Cloud at full scale).

## Decision
We choose **Redis Streams** for our notification subsystem architecture.

## Consequences

### Pros (Advantages of Redis Streams):
*   **Lower Operational Complexity:** As we already run Redis, leveraging Redis Streams introduces significantly less operational overhead compared to Kafka, which would require managing a new distributed system (Kafka brokers, ZooKeeper/Kraft). This is critical given our small team with no dedicated infrastructure engineer.
*   **Faster Time to Value:** The team's existing familiarity with Redis will lead to a faster learning curve and quicker implementation within the 2-week constraint.
*   **Cost-Effective:** Redis Streams is a feature of Redis itself, avoiding the additional infrastructure costs associated with a separate Kafka cluster (especially for managed services). We can start with our existing Redis setup (though a dedicated instance for streams is advisable for production), keeping within our modest budget.
*   **Excellent for Real-time Features:** Redis's native Pub/Sub capabilities, combined with Streams, make it an ideal choice for integrating future real-time WebSocket push notifications, simplifying the architecture for that future requirement.
*   **Sufficient Delivery Guarantees:** Redis Streams supports consumer groups, enabling competing consumers and persistent message offsets. This allows us to achieve at-least-once delivery and implement exactly-once semantics for critical billing notifications through careful application-level idempotent processing and explicit `XACK` commands.
*   **Good Performance at Scale:** Redis Streams can handle high throughput, sufficient for our current and projected 10x traffic growth (up to 5000 req/s equivalent notifications).

### Cons (Disadvantages of Redis Streams):
*   **Potentially Lower Maximum Throughput:** While high, Redis Streams may not match Kafka's extreme throughput capabilities in highly specialized, ultra-high volume, disk-bound scenarios. However, this is not a current or immediate future requirement given our scale.
*   **In-Memory First:** Although Redis can persist data to disk, its primary strength is in-memory operations. For extremely long-term message retention or very large message backlogs, Kafka's disk-backed architecture might be more robust.
*   **Smaller Ecosystem:** The Redis Streams ecosystem, while growing, is not as mature or extensive as Kafka's, which has a vast array of connectors, tools, and integrations.

## Alternatives Considered

### 1. Apache Kafka

**Reasons for Rejection:**
*   **High Operational Complexity:** Kafka is a powerful but complex distributed system. Its deployment, configuration, monitoring, and scaling require specialized expertise (Kafka brokers, ZooKeeper/Kraft clusters, replication, partition management). Our team of 6, without a dedicated infrastructure engineer and no prior Kafka experience, would face a steep learning curve and significant operational burden, making it challenging to meet the 2-week time-to-value constraint.
*   **Steeper Learning Curve:** The team's complete lack of Kafka experience would require substantial investment in training and experimentation, delaying delivery of value.
*   **Higher Cost:** While self-hosting is an option, it compounds the operational complexity. Managed Kafka services (like Confluent Cloud) can become expensive at scale, exceeding our modest budget. Given the constraints, the cost of expertise and operational overhead outweighs the benefits at our current stage.
*   **Overkill for Current Needs:** While Kafka is excellent for extreme scale and a rich stream processing ecosystem, its full capabilities are beyond our immediate requirements and would introduce unnecessary complexity given our specific constraints.

While Kafka offers superior raw throughput and a more mature ecosystem for large-scale, enterprise-grade stream processing, the critical factors of team expertise, operational overhead, time to value, and budget strongly disfavor it for our current context.