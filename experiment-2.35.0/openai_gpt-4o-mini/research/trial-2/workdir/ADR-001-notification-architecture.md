# ADR 001: Notification Architecture Decision

## Status
Proposed

## Context
We are developing a notification subsystem for our SaaS project management platform that needs to meet strict requirements for reliability and performance. Current usage metrics report around 85,000 monthly active users and 2 million tasks created monthly, leading to peak loads of ~500 requests per second during business hours. The current synchronous notification handling within the HTTP request cycle is leading to timeout issues, silent failures, cascading failures, and lacking delivery guarantees, especially for billing notifications. Our primary goals for this new subsystem include decoupling notifications from the request cycle, ensuring reliable delivery (at-least-once for all notifications, exactly-once for billing events), and enabling the capability for real-time WebSocket push notifications. We are choosing between two potential solutions: **Apache Kafka** and **Redis Streams**.

## Decision
After evaluating both options, we recommend implementing **Redis Streams** for the notification subsystem. This decision is based on Redis Streams' existing integration within our architecture, its speed, and the team's familiarity with the technology. Additionally, Redis provides a simpler operational overhead compared to Apache Kafka, given the current team’s capabilities and the budget constraints.

## Consequences**
### Pros of Redis Streams**
- **Familiarity:** The team has existing experience with Redis, reducing the learning curve and setup time.
- **Integration:** Redis Streams can be integrated into our current infrastructure without significant changes, leveraging the existing Redis instance used for caching.
- **Operation:** Redis is simpler to manage and deploy, keeping operational costs low and resources focused on development.
- **Performance:** Offers high throughput with sub-millisecond latencies suitable for our requirements without a significant performance impact.
- **Reliable persistence:** Using Redis Streams, we can implement message persistence and a dead-letter queue system, ensuring failed messages can be retried correctly.

### Cons of Redis Streams**
- **Lack of Advanced Features:** Redis Streams does not provide built-in exactly-once delivery semantics compared to Kafka, requiring additional mechanisms to ensure these semantics are maintained for critical billing notifications.
- **Scalability:** Although Redis can handle substantial loads, it is less scalable horizontally compared to Kafka, potentially requiring a reevaluation of future growth strategies.

## Alternatives Considered
### Apache Kafka**
- **Rejection Reason:** While Kafka offers features like topic partitioning, consumer groups, built-in exactly-once semantics, and better horizontal scalability, it introduces complexity that is not justifiable for our team size and experience. The lack of Kafka expertise and budget constraints (limited to a self-managed solution without full-scale managed services) would significantly increase the migration/setup time, likely exceeding our two-week constraint before delivering initial value. Additionally, operational complexity would be too high for our current team structure without a dedicated infrastructure engineer.

In conclusion, implementing Redis Streams, while requiring some careful handling to maintain exactly-once delivery for billing notifications, aligns best with our existing infrastructure, team capabilities, and immediate business goals.