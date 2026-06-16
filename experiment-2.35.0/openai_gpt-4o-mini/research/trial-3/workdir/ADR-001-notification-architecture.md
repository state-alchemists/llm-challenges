# Notification Subsystem Architecture Decision Record 

## Status
Proposed

## Context
The notification subsystem of our SaaS project management platform is responsible for sending emails and webhooks for task updates. As our user base has grown to 85,000 monthly active users, we've encountered various issues: request timeouts during peak usage, silent failures in notification deliveries, cascading failures due to webhook timeouts, and a lack of delivery guarantees for critical notifications. We need a solution to decouple this subsystem from our synchronous HTTP request cycle and handle anticipated growth while ensuring reliability and efficiency.

Key requirements include:
- Decoupling notifications from the request cycle for asynchronous processing.
- Supporting retries with exponential backoff for failed deliveries.
- Ensuring at-least-once and ideally exactly-once delivery semantics for critical notifications.
- Adding real-time WebSocket push notifications in the near term.
- Preparing for a 10x increase in load without major re-architecting.

## Decision
After careful consideration, we recommend using **Redis Streams** for our notification subsystem.

### Justification for Redis Streams:
1. **Familiarity**: The engineering team already uses Redis for session management. This reduces the learning curve and operational overhead associated with deploying a new technology like Kafka.
2. **Setup Time**: Implementing Redis Streams can be achieved within the two-week timeframe with little additional infrastructure setup, leveraging existing Redis setup.
3. **Operational Complexity**: Redis is simpler to operate and can be managed with fewer resources compared to Kafka, especially since we do not have a dedicated infrastructure engineer on the team.
4. **Message Retention and Consumer Groups**: Redis Streams allows us to retain messages for a configurable duration and supports multiple consumer groups, which is essential for our billing notifications to be processed independently.
5. **Exactly-Once Delivery**: Although Redis Streams do not inherently provide exactly-once delivery, we can implement additional transactional patterns (e.g. using Lua scripts) that can help achieve a similar guarantee for critical notifications through Redis transactions.
6. **Performance**: Redis is designed for high performance, providing low-latency message delivery, which is ideal for our use case, allowing us to handle peak loads efficiently.

## Consequences
### Pros:
- Leveraging existing knowledge of Redis within our team will allow for faster implementation and reduce operational risk.
- Lower setup complexity leads to a quicker time-to-value.
- Redis’ high throughput and low latency will meet our current needs and help manage future scaling challenges.

### Cons:
- Redis Streams does not inherently provide the same level of delivery guarantees as Kafka (e.g., partitioning and consumer tracking).
- We might need to implement additional mechanisms (e.g., in-memory caching of failed deliveries) to handle exactly-once delivery guarantees for billing notifications.

## Alternatives Considered
**Apache Kafka**: While Kafka offers robust features for message durability, high throughput, and excellent actual use cases for asynchronous event processing, it poses significant challenges given our current constraints:
- The engineering team lacks Kafka experience, which would require a learning period extending beyond our preferred two weeks.
- Higher operational complexity and infrastructure management burden due to its distributed nature.
- The projected costs for managed services are outside our current budget constraints.

In conclusion, choosing Redis Streams aligns better with our current team capabilities, budget, and operational requirements, allowing us to swiftly implement a more reliable notification subsystem.