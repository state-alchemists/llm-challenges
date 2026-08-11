# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
Our SaaS project management platform, serving 85,000 monthly active users and processing ~2M tasks per month, currently handles notifications synchronously within the HTTP request cycle. This approach has led to significant issues:

1.  **Request timeouts and high latency:** Notifications block the main request, causing average latencies of 800ms and spikes up to 8 seconds during peak loads (500 req/s).
2.  **Silent failures:** If external services (email providers, webhooks) are unavailable, notifications are silently dropped without retry mechanisms or dead-letter queuing.
3.  **Cascading failures:** Slow external webhook endpoints have previously led to connection pool exhaustion and outages in unrelated parts of the system.
4.  **Lack of delivery guarantees:** Critical notifications (e.g., "trial expired", "payment failed") require exactly-once delivery, which the current system cannot provide.

To address these issues and support future growth (10x traffic increase, real-time WebSocket push notifications within 2 quarters), we need to decouple notification processing, implement robust retry mechanisms, and guarantee reliable delivery. Specifically, at-least-once delivery is required for billing events, with exactly-once delivery where feasible.

**Key Constraints:**
*   **Team:** 6 engineers (3 senior, 3 mid-level), no dedicated infrastructure expertise.
*   **Existing Infrastructure:** Already use Redis in production for session management and rate limiting.
*   **Kafka Experience:** No prior team experience with Kafka.
*   **Timeline:** Max 2 weeks for initial setup and migration to deliver value.
*   **Budget:** Modest, ruling out expensive managed Kafka solutions at scale.
*   **Criticality:** Exactly-once semantics for billing notifications is a hard requirement.

## Decision
We have decided to implement the notification subsystem using **Redis Streams**.

This decision is primarily driven by the team's existing familiarity with Redis, the modest budget constraints, and the need for rapid implementation. While Apache Kafka offers a more feature-rich and robust solution for high-throughput distributed systems, its operational complexity and the team's lack of experience with it present significant barriers given our current constraints.

Redis Streams provides sufficient capabilities to address our immediate problems, including asynchronous processing, persistent message storage, consumer groups, and mechanisms for retries and dead-letter queues. Its lightweight nature and ease of integration with our existing Redis setup will allow us to deliver value quickly and within the allocated budget and team expertise.

## Consequences

### Pros:
*   **Low Operational Overhead:** The team already manages Redis, reducing the learning curve and operational burden significantly. Redis Streams is a native feature, avoiding the complexity of deploying and managing a separate distributed system like Kafka.
*   **Rapid Implementation:** Leveraging existing Redis infrastructure and team knowledge will enable us to meet the 2-week setup/migration timeline for initial value delivery.
*   **Cost-Effective:** Utilizing existing Redis instances or easily scalable Redis clusters is more budget-friendly than managed Kafka services or self-hosting Kafka.
*   **Asynchronous Processing:** Decouples notification sending from the HTTP request cycle, resolving request timeouts and improving user experience.
*   **At-Least-Once Delivery:** Redis Streams' consumer groups and acknowledgment mechanisms natively support at-least-once delivery, crucial for billing events.
*   **Exactly-Once Semantics (Feasible):** While Redis Streams does not offer exactly-once semantics out-of-the-box like Kafka transactions, it can be achieved for critical notifications (e.g., billing) through careful application-level idempotent processing and robust acknowledgment strategies. This is a trade-off we are willing to manage at the application layer for specific high-value messages.
*   **Real-time Capabilities:** Redis is well-suited for real-time applications, which aligns with our future goal of adding WebSocket push notifications.

### Cons:
*   **Scalability Limitations (Compared to Kafka):** While Redis Streams can handle significant throughput, it may not scale horizontally to the same extreme levels as a dedicated distributed log like Kafka without careful sharding and architecture. However, it is expected to handle 10x traffic growth for the foreseeable future.
*   **Feature Set:** Redis Streams has a less mature and comprehensive ecosystem compared to Kafka (e.g., schema registry, advanced monitoring, robust connectors). This may require more custom development for certain features.
*   **Exactly-Once Complexity:** Achieving strong exactly-once guarantees for complex scenarios might require more effort at the application level compared to Kafka's transaction API.
*   **Message Retention:** Redis Streams' default behavior for message retention might need careful configuration and management to avoid excessive memory usage, especially with high message volumes and long retention periods, requiring proactive monitoring.

## Alternatives Considered

### Apache Kafka

**Reasons for Rejection:**

*   **High Operational Complexity:** Kafka is a powerful but notoriously complex distributed system to operate, especially for a team without dedicated infrastructure engineers or prior experience. Setting up, monitoring, scaling, and maintaining Kafka clusters (even with tools like ZooKeeper/Kraft) would require a significant learning curve and ongoing effort.
*   **Lack of Team Experience:** The absence of any Kafka experience within our 6-person engineering team poses a substantial risk to the success and timeline of the project. Training and upskilling would consume valuable time, potentially exceeding the 2-week initial value delivery constraint.
*   **Budget Constraints:** While self-hosting is an option, it contradicts the operational complexity concern. Managed Kafka solutions like Confluent Cloud can be expensive, especially at scale, and are currently outside our modest budget.
*   **Overkill for Initial Needs:** For our current scale and immediate problems, the full power and complexity of Kafka might be an over-engineered solution. While it handles extremely high throughput and offers strong guarantees, the overhead associated with it outweighs the benefits for our initial requirements.
*   **Setup/Migration Time:** The initial setup, integration, and migration efforts for Kafka would very likely exceed the 2-week timeline, delaying crucial improvements to our notification system.

While Kafka offers superior throughput, robust ordering guarantees, strong exactly-once semantics via transactions, and a mature ecosystem with extensive connectors and monitoring, the operational complexity, lack of team experience, and budget constraints make it an unsuitable choice for our immediate needs and constraints.