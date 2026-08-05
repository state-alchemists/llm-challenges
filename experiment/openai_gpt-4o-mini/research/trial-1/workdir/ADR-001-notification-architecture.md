# Notification Architecture Decision Record

## Status
Proposed

## Context
The current notification module for our SaaS project management platform relies on synchronous processing, leading to significant latency issues (average latency of 800ms, spikes to 8s), silent failures, cascading failures, and the absence of delivery guarantees for critical notifications. As our user base grows, the need to decouple notifications from the HTTP request cycle becomes imperative. Other requirements include supporting retry mechanisms with exponential backoff, ensuring at-least-once delivery and exactly-once semantics for billing notifications, and a scalable architecture capable of handling a 10x increase in traffic within 2 quarters. Given the constraints of a small team with limited experience in Kafka and a modest budget, two primary options for the new notification subsystem have been evaluated: Apache Kafka and Redis Streams.

## Decision
We recommend adopting **Redis Streams** for the notification subsystem. 
- **Justification:** Redis Streams aligns closely with our existing infrastructure, allowing for swift implementation with minimal additional overhead. The team is already familiar with Redis, which reduces the learning curve and setup time. Redis Streams provides adequate message retention, delivery guarantees, and supports consumer groups to manage notification delivery effectively, adhering to our requirements for retry and scaling. Furthermore, it integrates seamlessly with our existing usage of Redis and can handle real-time WebSocket push notifications as our system evolves.

## Consequences
### Pros
- **Fast implementation:** Leverage existing Redis infrastructure reduces migration/setup time and operational complexity
- **Familiarity:** Our team is already skilled in managing Redis, lowering the learning curve and risk associated with adopting a new technology.
- **Supports at-least-once delivery:** Redis Streams provides validations for message processing, allowing for retries and ensuring improved reliability for notifications.
- **Flexibility:** Can easily accommodate future scaling demands and new features like WebSocket notifications without requiring a complete overhaul of the current architecture.

### Cons
- **Limited message retention compared to Kafka:** While Redis Streams allows configurations for message retention, it may not match Kafka’s high throughput and long-term retention capabilities, which could be a concern if message volume and retention needs grow significantly.
- **Operational complexity in large-scale scenarios:** Redis may require careful optimization to handle extreme traffic scenarios efficiently if scaling exceeds estimates.

## Alternatives Considered
- **Apache Kafka:** Although Kafka offers superior throughput, durability, and ordered delivery with its topic-partition model, it presents a steep learning curve for the team and operational complexity. The need for initial setup and migration is expected to exceed the relatively short timeline we have set forth (2 weeks). Additionally, budget constraints prevent leveraging managed services like Confluent Cloud at full scale. The lack of in-house expertise would likely increase risk and time required during initial adoption.

In conclusion, Redis Streams is the clear choice for the required notification architecture due to its alignment with existing infrastructure, team skill set, and immediate needs, while Kafka's complexity and resource requirements make it less appealing given our constraints.