# ADR-001: Notification Architecture Decision

## Status
Proposed

## Context  
The notification subsystem for our SaaS project management platform currently processes notifications synchronously, causing significant latency during peak hours, loss of notifications on failures, and overall unreliability in delivering critical notifications. We require an asynchronous solution that supports retry mechanisms, ensures delivery guarantees (at-least-once and exactly-once semantics), and can be implemented within a limited timeframe and budget. With a peak demand reaching ~500 requests per second and an expectation of 10x traffic growth, the subsystem needs to be significantly more scalable and robust.

## Decision  
After evaluating **Apache Kafka** and **Redis Streams**, we recommend adopting **Redis Streams** for the notification subsystem. This choice is justified based on:
1. **Familiarity**: Our team already has experience running Redis in production, thus minimizing the learning curve and speeding up implementation.
2. **Operational Complexity**: Redis Streams can be deployed within our existing Redis infrastructure, avoiding the need to introduce a new system (Kafka), which lowers operational overhead and aligns with our team’s capability given no dedicated infrastructure engineer is available.
3. **Setup Timeline**: Redis Streams can be configured and become operational within the required two-week period, ensuring we deliver value quickly.
4. **Delivery Guarantees**: Redis Streams support at-least-once delivery semantics through acknowledgment mechanisms, which aligns well with our requirements for billing notifications.

## Consequences  
### Pros
- **Reduced Latency**: By decoupling the notification process from synchronous operations, we will better respond to client requests, alleviating timeouts and enhancing user experience.
- **Built-in Reliability**: With retry capabilities and acknowledgment features, failed notifications can be retried automatically without losing important messages.
- **Cost-Effective**: Leveraging our existing Redis setup keeps costs down compared to the infrastructure costs associated with Kafka. 
- **Minimal Learning Curve**: The engineering team can quickly transition without the need for extensive training on Kafka.

### Cons
- **At-Least-Once Semantics**: Although Redis Streams can provide at-least-once delivery, achieving exactly-once semantics will require additional application-level management (e.g., deduplication).
- **Potential Scaling Limits**: Redis is generally limited in high-throughput scenarios compared to Kafka, which could pose challenges if unexpected growth beyond our projections occurs.

## Alternatives Considered  
### Apache Kafka  
Kafka was considered primarily for its high throughput and strong capabilities for event streaming, including support for exactly-once semantics and high scalability. However, several factors led to its rejection:
- **Learning Curve**: The team has no experience with Kafka, which would require considerable time and effort for training and knowledge transfer, likely exceeding our timeline constraints.
- **Operational Complexity**: Managing a Kafka cluster requires more operational overhead, which is not feasible given we lack dedicated infrastructure support.
- **Implementation Time**: The setup and migration period would likely exceed two weeks, delaying our ability to deliver value to users.

Redis Streams are thus the preferred option due to a better alignment with our immediate operational capabilities, execution timeline, and cost constraints.