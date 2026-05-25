# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

**Context**
The current notification system, embedded synchronously within the HTTP request cycle of our Python/Flask monolith, is causing significant issues: request timeouts, silent failures, cascading failures due to slow external services, and a lack of delivery guarantees for critical notifications. We need to decouple notifications, implement retry mechanisms, and guarantee at-least-once delivery for all notifications, with exactly-once delivery for billing-critical events. The system must also support real-time WebSocket push notifications within six months and scale to 10x our current traffic.

Our engineering team consists of 6 people with no dedicated infrastructure engineer. We already operate Redis for session management and rate limiting, but lack experience with Kafka. The solution must be deployable within two weeks to deliver value and fit a modest budget, ruling out expensive managed Kafka services.

**Decision**
We will adopt **Redis Streams** for our notification subsystem.

This decision prioritizes the team's existing operational expertise with Redis, minimizing the learning curve and initial setup time, which are critical constraints given our team size and the two-week value delivery requirement. Redis Streams provides the necessary features for asynchronous processing, persistent message queues, consumer groups, and at-least-once delivery. While achieving true exactly-once semantics with Redis Streams requires careful application-level design (idempotent consumers and transaction management), it is feasible for our billing-critical notifications.

**Consequences**

**Pros:**
*   **Low Operational Overhead**: Leverages existing Redis infrastructure and team familiarity, significantly reducing setup time and ongoing maintenance compared to introducing Kafka.
*   **Fast Time to Value**: Can be implemented and integrated within the two-week timeframe due to existing Redis knowledge.
*   **Asynchronous Processing**: Decouples notification sending from the HTTP request cycle, resolving request timeouts and cascading failures.
*   **Retry Mechanism**: Easily implementable with consumer groups and explicit acknowledgement.
*   **At-Least-Once Delivery**: Achievable through consumer groups and message acknowledgement.
*   **Real-time Capabilities**: Redis's Pub/Sub and Streams are well-suited for future WebSocket integration.
*   **Cost-Effective**: Utilizes existing infrastructure, avoiding the high costs of managed Kafka solutions.

**Cons:**
*   **Exactly-Once Semantics (Application-level)**: While possible, achieving true exactly-once delivery for billing-critical notifications will require more diligent application-level design and implementation of idempotency than with Kafka.
*   **Scalability Challenges (Extreme Throughput)**: Redis Streams, while performant, may not scale as effortlessly as Kafka for extremely high throughput scenarios (billions of messages per day) without careful sharding and architecture. However, it meets our 10x growth target.
*   **Message Retention Management**: Requires manual management of stream length and message eviction to prevent unbounded memory growth, adding a minor operational task.
*   **Ecosystem Maturity (Compared to Kafka)**: The ecosystem of tools and connectors for Redis Streams is less mature than Kafka's, potentially requiring more custom development.

**Alternatives Considered**

**Apache Kafka**
Kafka was considered for its robust features, including native support for high throughput, strong ordering guarantees, and sophisticated exactly-once semantics. However, it was rejected due to several critical constraints:

*   **Team Expertise**: Our team has no prior Kafka experience. Introducing a new distributed system like Kafka would entail a significant learning curve, requiring more than the two-week setup/migration budget.
*   **Operational Complexity**: Kafka is notoriously complex to set up, operate, and maintain, especially for a team without a dedicated infrastructure engineer. This would divert critical engineering resources from product development.
*   **Budget Constraints**: Managed Kafka services (like Confluent Cloud) that would mitigate operational complexity are beyond our modest budget for full-scale deployment. Self-hosting Kafka would exacerbate operational challenges.
*   **Time to Value**: The time required to learn, deploy, and integrate Kafka would exceed our two-week target for delivering value, delaying critical fixes to our notification system.

While Kafka offers superior native support for complex distributed messaging patterns and higher theoretical throughput, the immediate operational and expertise constraints of our team make Redis Streams the more pragmatic and effective choice for the next 1-2 years of our product growth.