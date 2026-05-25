**Title**: ADR-001: Notification Subsystem Architecture
**Status**: Proposed

**Context**
The existing synchronous notification module in our Python/Flask monolith is causing request timeouts, silent failures, and cascading failures due to blocking HTTP requests for email and webhook dispatch. There are no delivery guarantees, which is critical for billing-related notifications. The system needs to decouple notifications, implement retry mechanisms, ensure at-least-once delivery (and exactly-once for billing events), and scale for 10x traffic growth, including future real-time WebSocket push notifications.

Key constraints include an engineering team of 6 with no dedicated infrastructure engineer and no prior Kafka experience. We currently operate Redis for session management and rate limiting. The solution must provide value within two weeks, adhere to a modest budget, and guarantee exactly-once semantics for billing notifications.

**Decision**
We will implement the notification subsystem using **Redis Streams**.

This decision is based on the following justifications:
1.  **Existing Infrastructure & Team Familiarity**: The team already uses and operates Redis in production, reducing the operational overhead and learning curve. This directly addresses the constraint of having no dedicated infrastructure engineer and no Kafka experience, allowing for a faster setup and migration (within the 2-week target).
2.  **Exactly-Once Semantics (Feasible)**: While Redis Streams inherently provide at-least-once delivery, careful implementation with consumer groups and idempotent consumers allows for achieving exactly-once processing for critical billing notifications, aligning with our strict requirement. The ability to track consumer offsets within Redis itself simplifies this.
3.  **Scalability**: Redis Streams offer robust scaling capabilities through consumer groups, allowing multiple consumers to process messages from a stream in parallel. This will accommodate the projected 10x traffic growth without requiring a complete re-architecture.
4.  **Real-time Capabilities**: Redis's pub/sub and stream capabilities are well-suited for future real-time WebSocket push notifications, simplifying the integration of new features.
5.  **Cost-Effectiveness**: Given the modest budget, leveraging our existing Redis instance is significantly more cost-effective than deploying and managing a new Kafka cluster, especially considering the inability to afford managed Confluent Cloud at full scale.

**Consequences**
*   **Pros**:
    *   **Reduced Operational Overhead**: Leverages existing Redis infrastructure and team knowledge.
    *   **Faster Time to Value**: Low setup and migration effort, fitting within the 2-week constraint.
    *   **Cost-Effective**: No new infrastructure costs for a separate message broker.
    *   **Strong Support for Real-time**: Excellent foundation for future WebSocket push notifications.
    *   **Reliable Delivery**: Supports at-least-once delivery with mechanisms for exactly-once processing with careful implementation.
*   **Cons**:
    *   **Complexity of Exactly-Once**: While achievable, implementing true exactly-once semantics requires careful design of idempotent consumers and offset management, which can add development complexity.
    *   **Limited Ecosystem Compared to Kafka**: The ecosystem around Redis Streams, while growing, is not as mature or extensive as Kafka's for certain advanced use cases (e.g., complex stream processing, long-term data retention for analytics).
    *   **Potential for Operational Burden at Extreme Scale**: While Redis Streams scale well, at extremely high throughputs or for very long message retention, a self-managed Redis cluster might eventually become an operational burden compared to a fully managed Kafka solution (which is currently out of budget).

**Alternatives Considered**

**Apache Kafka**:
Kafka was considered due to its industry-standard position for high-throughput, fault-tolerant message queues and robust support for distributed stream processing, consumer groups, and strong delivery guarantees (including exactly-once semantics out-of-the-box in many client libraries).

However, Kafka was rejected due to:
1.  **High Operational Complexity**: Deploying, managing, and monitoring a Kafka cluster requires specialized knowledge and dedicated infrastructure engineering, which our 6-person team currently lacks. This conflicts with the "no dedicated infrastructure engineer" constraint.
2.  **Steep Learning Curve**: The team has no Kafka experience, making the initial setup and migration significantly longer than the stipulated 2-week target for delivering value.
3.  **Budget Constraints**: Managed Kafka solutions like Confluent Cloud are currently beyond our modest budget, and self-hosting would introduce significant operational costs in terms of time and expertise.
4.  **Overkill for Initial Needs**: While Kafka offers powerful features, its full capabilities are likely an overkill for the immediate notification decoupling and retry requirements, especially considering the operational overhead for our team size. The benefit of its advanced features did not outweigh the increased complexity and cost for our current needs and team constraints. While Redis Streams require more careful implementation for certain guarantees, the immediate operational cost and learning curve are significantly lower.