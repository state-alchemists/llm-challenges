# ADR-001: Notification Architecture Decision

## Status
Proposed

## Context
Our SaaS project management platform currently handles notifications synchronously within the HTTP request cycle, leading to request timeouts, silent failures, cascading failures, and a lack of delivery guarantees. We need a solution that can decouple notifications from this cycle, offer reliable message delivery (at least once for most notifications, exactly once for billing-critical ones), support retries with exponential backoff, and scale to handle a tenfold increase in traffic. Our engineering team consists of six members with varying experience, and we currently utilize Redis, but lack Kafka experience. Budget constraints limit us from using managed solutions like Confluent Cloud.

## Decision
We will adopt **Redis Streams** for the notification subsystem. Redis Streams is well-suited for our use case due to its ease of integration with our existing Redis infrastructure and the team's familiarity with Redis. It provides support for at-least-once delivery, message persistence, consumer groups, and can scale horizontally.

## Consequences 
### Pros
- **Integration**: We can leverage our existing investment in Redis, reducing setup time as we do not need to introduce a new technology stack.
- **Simplicity**: The operational complexity is lower, given the team's experience with Redis. This ensures that we can implement changes quickly and reduce the time to deliver value.
- **Performance**: Redis Streams allows for high throughput and low latency, making it capable of handling peak traffic effectively.
- **Message Retention**: Supports persistence, enabling us to recover from failures without losing messages.
- **Supported Features**: Supports consumer groups and message acknowledgment, which are crucial for implementing retry logging.

### Cons
- **Delivery Guarantees**: While Redis Streams provides at-least-once semantics, achieving exactly-once semantics may require implementing additional complex logic in our application layer, like idempotency.
- **Scaling Challenges**: Redis streams may have operational challenges when scaling horizontally, especially with a significant influx of traffic where larger partitions need to be managed carefully.

## Alternatives Considered
### 1. Apache Kafka
Kafka was considered due to its strong guarantees around message delivery and high throughput, making it suitable for use cases requiring reliability and ordering guarantees for billing events. However, the team has no experience with Kafka, necessitating extensive training and operational adjustments that would exceed our two-week migration timeline and could delay critical work. Additionally, Kafka's setup and management complexity is high, requiring more dedicated infrastructure support than we currently have.

Given the above analysis, Redis Streams presents the best balance between operational feasibility, performance, and meeting our requirement for reliable notifications within the team's existing skill set and project constraints.