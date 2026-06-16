# ADR-001: Notification Architecture

## Status
Proposed

## Context
The current notification system for our SaaS project management platform handles email and webhook notifications synchronously within the HTTP request cycle. This approach leads to request timeouts, silent failures, cascading failures from slow endpoints, and a lack of delivery guarantees for critical notifications. As the monthly active user count grows, the system needs to evolve to handle increased traffic and ensure timely and reliable notifications.

### Requirements
- Decoupling notification processes from the HTTP request cycle for asynchronous handling.
- Implementing retry mechanisms with exponential backoff for failed notifications.
- Ensuring at-least-once delivery guarantees for critical billing events and striving for exactly-once delivery.
- Accommodating real-time WebSocket notifications.
- Managing 10x traffic growth over the next few years.

### Constraints
- A limited engineering team without extensive Kafka experience.
- Existing usage of Redis for caching purposes.
- Budget constraints preventing large-scale systems or managed services like Confluent Cloud.
- A necessity to deliver value within two weeks, limiting the scope of potential solutions.

## Decision
After evaluating **Apache Kafka** and **Redis Streams**, I recommend implementing **Redis Streams** for the notification subsystem due to its ease of integration and inherent support for scaling asynchronous workloads without steep operational overhead.

### Justification
- **Familiarity**: The engineering team already has experience with Redis, reducing the learning curve and setup time.
- **Throughput**: Redis Streams can handle high throughput, making it suitable as we anticipate increased traffic.
- **Delivery Guarantees**: While Redis Streams provides at-least-once message delivery through acknowledgement features, it also allows for implementing retry logic in a straightforward manner.
- **Operational Complexity**: Integrating Redis Streams is less complex than setting up Kafka for a team without extensive Kafka experience. Its operations largely involve our current Redis infrastructure.
- **Setup Time**: Implementing Redis Streams can be achieved within the required two-week timeframe without the need for extensive modifications to existing components.

## Consequences
### Pros
- Existing team can leverage their knowledge of Redis, reducing onboarding time and friction.
- Redis Streams offers the ability to easily control message flow and implement retry strategies where needed.
- The system is extensible, allowing for future enhancements like WebSocket notifications with minimal adjustments.

### Cons
- While offering at-least-once delivery guarantees, achieving exactly-once semantics will require additional effort and considerations in the application logic.
- Potential limitations on retention policies when compared to Kafka, which is designed with more extensive retention capabilities suited for large data volumes.

## Alternatives Considered
**Apache Kafka**: While Kafka excels in high-throughput environments with strong retention and exactly-once delivery guarantees, the lack of experience within the current engineering team would lead to a longer setup period, higher operational complexity, and possibly a slower path to achieving the necessary improvements in the notification system. Given the moderate budgetary constraints, this choice may not provide sufficient immediate value to justify the investment in training and resource allocation.
