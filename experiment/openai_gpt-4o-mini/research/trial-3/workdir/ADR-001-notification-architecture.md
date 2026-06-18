# ADR-001: Notification Architecture Decision

## Status
Proposed

## Context
The need has arisen to improve the notification subsystem of our SaaS project management platform. The current implementation, which sends notifications synchronously within the HTTP request cycle, leads to significant latency issues, silent failures, and cascading failures that disrupt service. As the user base grows (with a peak load of ~500 req/s), we require a robust solution that can handle at least 10x traffic growth without architectural overhaul. Additionally, the platform needs features such as retry mechanisms with exponential backoff, guaranteed delivery (at-least-once for all notifications, exactly-once for billing-critical notifications), and real-time WebSocket push notifications within two quarters. The team consists of six engineers with a budget constraint and no prior experience with Apache Kafka.

## Decision
We recommend adopting **Redis Streams** as the new notification subsystem. This choice is based on the team's existing familiarity with Redis, avoiding the steep learning curve associated with Apache Kafka, and the meaningful capabilities Redis Streams provide for our use case. Redis Streams support message delivery guarantees, including acknowledgement and consumer groups. Additionally, it allows us to implement through exponential backoff strategies effectively, which aligns with our requirement for better reliability in notifications.

## Consequences
### Pros:
- **Familiarity:** Leveraging Redis Streams allows the team to work with a tool they already use, minimizing setup and ongoing maintenance complexity.
- **Operational simplicity:** Redis Streams is simpler to deploy and manage compared to Kafka, which requires a more complex setup, especially without dedicated infrastructure support.
- **Efficient for the required workloads:** Redis Streams can handle high throughput (potentially in millions of messages per second according to specifications), which is ideal to accommodate the projected growth.
- **Flexible delivery guarantees:** Supports at-least-once semantics out of the box, with mechanisms for message acknowledgment and the ability to replay messages.
- **Integration with existing stack:** Existing Redis infrastructure can be repurposed, requiring less migration effort and fitting within the budget constraints.

### Cons:
- **Exactly-once semantics may require additional handling:** Configuring Redis Streams for exactly-once delivery semantics could involve managing idempotency explicitly in our application code, which adds some complexity.
- **Lesser scalability compared to Kafka:** While Redis Streams are powerful, they may not scale as well as Kafka for very high volume scenarios; this could be a bottleneck if traffic exceeds projected growth significantly in the future.

## Alternatives Considered
1. **Apache Kafka**  
   - **Rejection reason:** Although Kafka offers strong durability, high throughput, and exactly-once semantics, it introduces considerable operational complexity that our engineering team is unprepared for within the current resource constraints. The steep learning curve and two-week setup time required to achieve effective use would likely delay our delivery timelines, while the budget does not allow for a managed solution. Moreover, without existing Kafka experience on the team, the risks associated with operational management are high, especially considering the requirements for urgent system reliability and scalability.  

In conclusion, Redis Streams is strategically aligned with our operational requirements, existing infrastructure, and growth targets, putting us in a strong position to ensure reliable notifications with manageable complexity.