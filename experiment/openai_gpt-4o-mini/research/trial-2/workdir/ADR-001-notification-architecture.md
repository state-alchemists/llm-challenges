# Notification Architecture Decision Record

## Status
Proposed

## Context
The notifications module of our SaaS project management platform currently processes notifications synchronously, leading to request timeouts, silent failures, and cascading failures. We require a new architecture that decouples this functionality from HTTP request handling to support at-least-once delivery guarantees, especially for billing-critical notifications, while enabling real-time WebSocket notifications. The engineering team consists of 6 members without Kafka experience, and we aim for a solution that can be implemented in less than two weeks.

## Decision
We will implement **Redis Streams** as the notification subsystem. While Apache Kafka offers robust features, its complexity and our team's unfamiliarity with it create overhead that we cannot afford given our current constraints. Redis Streams leverages our existing Redis infrastructure, allowing for asynchronous notification processing with minimal setup.

## Consequences
### Pros
- **Familiarity**: Teams already have operational experience with Redis, reducing the learning curve.
- **Integration and setup**: Quick to integrate into the existing architecture, leveraging current Redis instances, and accommodating setup within two weeks.
- **Data structure**: Redis Streams support message retention and the capability to manage consumer groups, offering the ability to replay messages in case of failures.
- **Performance**: Suitable for high-throughput operations required by our scaling target of 10x growth.
- **Exactly-once semantics**: With appropriate handling and acknowledgments, we can approach exactly-once delivery for billing notifications.

### Cons
- **Limited features**: Redis Streams lacks some of the advanced features of Kafka, like log compaction and partitioning.
- **Message management complexity**: Handling message acknowledgment and retries will add development overhead compared to Kafka's built-in functionalities.
- **Scalability concerns**: While Redis can handle significant loads, it may not scale as seamlessly as Kafka in terms of distributed systems.

## Alternatives Considered
**Apache Kafka**: While Kafka offers high throughput, ordering guarantees, and built-in distributed scaling capabilities, it comes with operational complexity and a learning curve that our team cannot accommodate at this time. The two-week timeline for implementing a critical service will likely be unattainable with Kafka, given our team's lack of experience and the need for extensive operational knowledge to manage Kafka effectively. This led to the decision to opt for Redis Streams, which aligns better with our team's capabilities and immediate needs.
