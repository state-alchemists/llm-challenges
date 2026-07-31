# ADR 001: Notification Architecture Decision

## Status
Proposed

## Context
Our SaaS project management platform currently sends notifications (emails and webhooks) synchronously within the HTTP request cycle. With 85,000 monthly active users generating ~2M tasks per month peak load, this architecture causes significant problems:
1. **Request timeouts**: Notifications block responses, leading to unacceptable latencies.
2. **Silent failures**: Notifications may be dropped if external services fail.
3. **Cascading failures**: Slow external services can exhaust connection pools, affecting other features.
4. **No delivery guarantees**: Critical notifications lack at-least-once delivery assurances, resulting in potential revenue loss.

To address these issues, the team aims to decouple the notification system from the request cycle, support retry mechanisms, and ensure both at-least-once and exactly-once delivery for billing notifications.

## Decision
We recommend implementing **Redis Streams** for the notification subsystem.

### Justification
1. **Familiarity**: Since the team already operates Redis for session management and rate limiting, leveraging Redis Streams minimizes the learning curve. 
2. **Setup Time**: Redis Streams can be integrated and operational within the required two-week timeframe, using existing infrastructure to facilitate swift implementation.
3. **Performance**: Redis Streams can handle high throughput and supports consumer groups for parallel processing, easing peak load management.
4. **Delivery Guarantees**: Although Redis Streams provide at-least-once delivery, exactly-once semantics can be achieved through idempotent updates when processing billing notifications.

In contrast, Kafka would require substantial effort to integrate into the current architecture. The engineering team lacks Kafka experience, which could prolong the setup and operational training.

## Consequences
### Pros of Redis Streams
- Fast deployment and low operational complexity leveraging existing knowledge.
- Fulfills at-least-once delivery requirements; can implement exactly-once with careful development.
- Supports real-time features and can grow as traffic increases, catering to the scaling target of 10x.

### Cons of Redis Streams
- Limited retention period compared to Kafka, which might necessitate careful management of stream cleanup and data lifespan.
- At-least-once delivery may lead to duplicate notifications unless handled correctly, requiring extra checks for idempotency.

## Alternatives Considered
**Apache Kafka** was considered but ultimately rejected due to:
- **Complexity**: Requires considerable infrastructure and configuration overhead.
- **Knowledge Gap**: The team has no prior Kafka experience, leading to a steep learning curve that could hinder timely implementation.
- **Cost**: Utilizing a managed Kafka service (like Confluent Cloud) would exceed budget constraints, and self-hosting Kafka with the existing team size might lead to operational challenges.