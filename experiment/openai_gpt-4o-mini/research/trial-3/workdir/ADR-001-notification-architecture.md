# ADR 001: Notification Architecture Decision

## Status
Proposed

## Context
The notifications module of our SaaS project management platform handles sending emails and webhooks to inform users about updates to tasks. Currently, notifications are sent synchronously within the HTTP request cycle, leading to increased latency (average of 800ms, spikes to 8s) and poor user experience. Additionally, silent failures and cascading failures have occurred, manifesting as dropped notifications without retries or dead-letter queues, compromising billing-critical notifications. The goal is to decouple notifications from the request cycle, support retries with exponential backoff, guarantee at-least-once delivery for critical events, and establish a scaling capacity for up to 10x growth, while adhering to our budget and existing technology constraints.

## Decision
We choose **Redis Streams** as the notification subsystem over **Apache Kafka**. This decision rests on several key factors:
- **Familiarity**: Our team has existing production experience with Redis, which minimizes the learning curve and operational overhead.
- **Setup Time**: Redis Streams can be integrated and operational within the constraint of 2 weeks, while Kafka would require more setup time and expertise not readily available on the team.
- **Exactly-once Semantics**: Using Redis with Lua scripts allows us to implement exactly-once delivery semantics efficiently in our use case. 
- **Operational Complexity**: Redis Streams offers lower operational complexity compared to managing a Kafka cluster without dedicated infrastructure engineers.

## Consequences
### Pros
- **Lower Latency and Simplicity**: Operations involving Redis Streams are typically simpler and faster, leading to improved performance and user experience.
- **Existing Infrastructure**: We leverage existing Redis infrastructure for session and rate limiting, avoiding unnecessary overhead of introducing a completely new system.
- **User-friendly Requirements**: Developers can focus on business logic without the complexity of maintaining Kafka brokers.

### Cons
- **Scalability**: Redis Streams may not handle extremely high throughput as efficiently as Kafka in scenarios requiring massive scaling.
- **Limited Features**: Compared to Kafka, there may be limitations in message retention and consumer group handling, particularly under larger loads.

## Alternatives Considered
- **Apache Kafka**: While Kafka offers higher scalability, message retention policies, and superior fault tolerance, it requires significant operational overhead and investment in terms of time and resources for our current engineering capabilities.  Our team lacks Kafka experience, which would extend setup time beyond our capacity. Moreover, the budget constraints on a managed Kafka solution further complicate this option. Given these factors, we believe Kafka is not viable at this stage.

This ADR serves as a structured approach to evaluate our notification subsystem needs and a definitive choice based on the specific constraints and requirements outlined.