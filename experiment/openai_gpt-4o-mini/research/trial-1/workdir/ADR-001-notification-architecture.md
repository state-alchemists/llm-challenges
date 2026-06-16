# Notification Architecture Decision Record

## Title
Notification Subsystem Architectural Choices

## Status
Proposed

## Context
The current notification system in our SaaS project management platform is synchronous, resulting in increased latencies and request timeouts during peak usage. Key problems include silent failures, cascading failures affecting the stability of unrelated features, and the lack of delivery guarantees, especially for billing-critical notifications. The goal is to decouple notifications from the HTTP request cycle, ensuring asynchronous processing, supporting retries, and maintaining exactly-once delivery for vital messages.

## Decision
We have decided to implement **Redis Streams** as the notification subsystem for the following reasons:
1. **Familiarity and Ease of Use**: Our engineering team already has experience with Redis, which reduces the learning curve and setup time. Redis Streams can be adopted within the stipulated two-week period without requiring extensive retraining or new infrastructure skills.
2. **Operational Simplicity**: Redis is already part of our infrastructure, allowing us to build on an existing solution without needing to manage a more complex system like Kafka.
3. **Delivery Guarantees**: Redis Streams support at-least-once delivery semantics and can be configured to implement exactly-once processing through careful consumption patterns and the use of Redis commands.

## Consequences
### Pros:
- **Reduced Latency**: Offloading notifications from the HTTP request cycle will improve user-facing latency significantly.
- **Operational Familiarity**: Leveraging existing Redis infrastructure minimizes the time required for deployment and troubleshooting.
- **Flexible Message Handling**: Redis Streams allow for easily adjusting the processing model, supporting retries with exponential backoff as needed.

### Cons:
- **Limited Scalability**: Although Redis can handle high throughput, it may not scale as seamlessly with 10x traffic growth compared to Kafka.
- **Complex Exactly-Once**: Implementing exactly-once semantics in Redis is more challenging than in Kafka, requiring careful management of acknowledgment and processing states.

## Alternatives Considered
1. **Apache Kafka**:
   - **Rejection Reason**: The complexity of managing Kafka, especially considering the lack of experience within the team, poses a significant risk and potential delays. Kafka would require a steep learning curve, and the operational overhead is not justifiable given our current resources and budget constraints.

In summary, the decision favors Redis Streams for its alignment with team capabilities, quicker time to value, and adequate support for our immediate needs despite some limitations in scalability and complexity of achieving exactly-once semantics for critical cases.