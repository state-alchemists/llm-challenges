# ADR 001: Notification Architecture

## Status
Proposed

## Context
We run a SaaS project management platform encountering challenges in our notifications module as usage has grown. The current implementation synchronously sends notifications during the HTTP request cycle, leading to request timeouts and dropped notifications. Key performance metrics include peak loads of ~500 requests per second, with an average latency of 800ms and spikes to 8s. We aim to decouple notifications from the HTTP request, implement retries with exponential backoff, guarantee at-least-once delivery for billing events, and adapt to 10x traffic growth. Constraints include a team of 6 without dedicated infrastructure engineers, existing Redis usage, need for timely implementation (within 2 weeks), budget limitations, and the maintenance of exactly-once delivery semantics for billing notifications.

## Decision
After evaluating the options, we will choose **Redis Streams** for the notification subsystem for the following reasons:
- **Familiarity and Support**: Our team already has experience with Redis, which reduces the ramp-up time for implementation, fitting within our two-week migration window.
- **Operational Complexity**: Using Redis minimizes the operational complexity that would come with introducing Kafka into our infrastructure, which the team has no prior experience with.
- **Performance**: Redis Streams provides sufficient throughput to handle expected traffic growth, supporting thousands of messages per second with low-latency reads and writes, which aligns with our need for performance.
- **Delivery Guarantees**: Redis Streams allows for at-least-once delivery semantics and consumer group support, enabling retries without dropping messages, crucial for billing notifications.
- **Integration Ready**: We are already using Redis for other functionalities, meaning overall maintenance and resource management will be easier with fewer systems in play.

## Consequences
**Pros**:
- Simple configuration and low operational overhead due to existing expertise.
- Fast message delivery and processing suitable for async operations.
- Reliable delivery mechanisms with retry capabilities and potential for exactly-once semantics.
- Quicker time to market due to no learning curve and existing Redis deployment.

**Cons**:
- Scalability may eventually become a concern as message volume increases further, requiring potential re-evaluation.
- Redis does not natively support message retention as comprehensively as Kafka, which might necessitate building a custom solution for long-term message storage.

## Alternatives Considered
**Apache Kafka** was considered due to its robustness and high throughput characteristics. However, due to the following reasons, it was ultimately rejected:
- Lack of team experience with Kafka could lead to a longer onboarding and implementation phase than our constraints allow.
- Higher operational complexity and resource requirements for managing Kafka, which would not suit a team without a dedicated infrastructure engineer.
- Cost implications for a managed Kafka solution would exceed our budget constraints.

In conclusion, Redis Streams is the most balanced choice for our notification subsystem, balancing our present needs with the resources we can effectively manage.