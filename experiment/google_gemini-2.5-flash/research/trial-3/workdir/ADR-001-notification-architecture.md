# ADR-001: Notification Subsystem Messaging Technology

## Status
Proposed

## Context
Our SaaS project management platform, serving 85,000 monthly active users and processing ~2M tasks per month (peaking at ~500 req/s), currently handles notifications synchronously within the HTTP request cycle. This architecture has led to:
1.  **Request timeouts:** Average latency of 800ms, with spikes up to 8 seconds during peak hours.
2.  **Silent failures:** Notifications are dropped without retry if external services (email providers, webhook endpoints) are unavailable.
3.  **Cascading failures:** Slow external services have caused connection pool exhaustion, leading to system outages.
4.  **No delivery guarantees:** Crucial billing-related notifications lack at-least-once or exactly-once delivery assurances.

To address these issues, we need to decouple notifications, implement retry mechanisms, guarantee at-least-once (and ideally exactly-once for billing events) delivery, support future real-time WebSocket push notifications, and scale to 10x current traffic.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We currently use Redis for session storage and rate limiting. There is no existing Kafka experience within the team. The solution must be implemented and deliver initial value within 2 weeks, operate within a modest budget (precluding expensive managed Kafka at full scale), and maintain exactly-once semantics for billing notifications.

## Decision
We choose **Redis Streams** as the messaging technology for the new notification subsystem.

## Consequences
### Pros
*   **Operational Familiarity & Reduced Overhead:** Leverages our existing Redis infrastructure and the team's familiarity with Redis. This significantly lowers the operational burden and learning curve, aligning with the constraint of having no dedicated infrastructure engineer and limited Kafka experience.
*   **Rapid Time to Value:** Redis Streams can be quickly integrated and configured, allowing us to meet the critical 2-week deadline for delivering initial value and decoupling notifications.
*   **Cost-Effectiveness:** Utilizing our existing Redis deployment minimizes additional infrastructure costs, fitting within our modest budget.
*   **Scalability for Current Needs:** Redis Streams can comfortably handle our projected 10x traffic increase (up to 5000 req/s peak), especially when deployed with appropriate Redis clustering or sharding strategies.
*   **Strong Foundation for Real-time:** Redis's capabilities, including Pub/Sub (which can complement Streams), provide a robust platform for integrating real-time WebSocket push notifications within our 2-quarter target.
*   **At-Least-Once Delivery:** Natively supports at-least-once delivery for messages through consumer groups and explicit acknowledgment, addressing the current silent failure problem.

### Cons
*   **Application-Level Exactly-Once Semantics:** While achievable, implementing exactly-once delivery for billing-critical notifications with Redis Streams will require more explicit application-level design (e.g., idempotent consumers, transaction logging, unique message IDs, and careful state management) compared to Kafka's more robust native transactional APIs.
*   **Message Retention Limitations:** Redis Streams are not designed for indefinite, petabyte-scale message retention typical of Kafka. While configurable, a long-term archival strategy may be necessary if regulatory compliance or auditing demands very old notification data.
*   **Throughput Benchmarks:** In theoretical extreme scaling scenarios (e.g., 100x traffic or specialized high-throughput messaging beyond our current scope), Redis Streams might eventually show performance limitations compared to a highly optimized Kafka cluster. However, this is beyond our current 10x growth target.

## Alternatives Considered
### Apache Kafka
*   **Rejection Reason:** Apache Kafka, while a powerful and industry-standard choice for high-throughput, highly durable messaging with strong guarantees (including robust native support for exactly-once semantics and long-term retention), was rejected primarily due to critical team and budget constraints. The engineering team has no prior Kafka experience and lacks a dedicated infrastructure engineer, making the operational complexity and steep learning curve a significant barrier. Self-hosting a Kafka cluster would require substantial time investment, likely exceeding our "2 weeks of setup/migration work" constraint and diverting critical resources from product development. While managed Kafka services exist, our "modest budget" constraint prevents the full-scale adoption of expensive offerings like Confluent Cloud. The operational overhead and the risk of misconfiguration or mismanagement with an inexperienced team outweigh Kafka's inherent technical advantages for our current context and immediate scaling needs.