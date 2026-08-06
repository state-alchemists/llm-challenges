# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification module for our SaaS project management platform processes notifications synchronously, leading to significant performance issues, including request timeouts, silent failures, cascading failures, and a lack of delivery guarantees for critical notifications. The architecture needs to evolve to support asynchronous processing, retries with exponential backoff, and delivery guarantees (at-least-once, and ideally exactly-once for billing notifications). Additionally, real-time WebSocket push notifications are planned, and the system should be able to handle a potential 10x increase in traffic. The engineering team consists of 6 members with limited experience in new technologies and budget constraints.

## Decision
After evaluating both Apache Kafka and Redis Streams, we chose **Redis Streams** as the notification subsystem's messaging solution.

### Justification
- **Familiarity**: The team already manages Redis in production, reducing onboarding and operational complexities compared to Kafka where prior experience is lacking.
- **Quick Setup**: Redis Streams can be implemented within the required two weeks without extensive training, allowing for faster time-to-value.
- **Throughput & Performance**: Redis can handle a high number of operations per second (up to 100k+ for a single instance), which is sufficient given the projected user growth and current load.
- **Ordering Guarantees**: Messages can be consumed in the order they are produced without the additional complexity of partitioning that Kafka requires.
- **Retention and Data Management**: Redis Streams supports configurable data retention policies, allowing us to maintain messages for a specified duration which fits our requirement for handling retries and failures.
- **Exactly-Once Semantics**: Implementing Lua scripts for transactional operations within Redis will help achieve exactly-once delivery semantics, particularly for critical billing notifications.

## Consequences
### Pros
- Low operational complexity due to existing Redis infrastructure.
- Reduced latency for user requests as notifications are processed asynchronously.
- Enhanced resilience with retry mechanisms in place.
- Ability to manage high throughput as user traffic grows.

### Cons
- Redis Streams lacks some advanced features of Kafka, such as partitioning and advanced consumer group management, that facilitate massive scale handling.
- Dependence on the Redis memory model potentially increases costs for larger data volumes, compared to distributed options like Kafka.

## Alternatives Considered
**Apache Kafka** was rejected for the following reasons:
- Steeper learning curve and time investment required for the team to become effective users of Kafka.
- It may be over-engineered for the current needs of the notification subsystem, introducing unnecessary complexity given the modest scale and budget constraints.
- Requires a budget for managed services if scaling beyond modest use cases, which we cannot afford.

In conclusion, choosing Redis Streams leverages existing infrastructure, aligns with team capabilities, and meets the necessary functional requirements effectively and efficiently.