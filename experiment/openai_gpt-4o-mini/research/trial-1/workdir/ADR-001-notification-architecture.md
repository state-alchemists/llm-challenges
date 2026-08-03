# ADR-001: Notification Architecture Decision

## Status
Proposed

## Context
The notifications system for our SaaS project management platform currently operates synchronously within the HTTP request cycle, leading to significant latency and reliability issues. Major challenges include request timeouts, silent failures of notifications, cascading failures affecting other features, and inadequate delivery guarantees for critical messages. With anticipated traffic growth and the need to support real-time WebSocket notifications, a new architecture for the notification subsystem is essential. The system also imposes constraints such as a limited engineering team size and existing infrastructure utilizing Redis.

## Decision
After evaluating the two options — **Apache Kafka** and **Redis Streams** — I recommend implementing **Redis Streams** as the notification subsystem. The decision is based on the following critical factors:

1. **Familiarity and Time-to-Value**: The engineering team is already experienced with Redis, which minimizes the learning curve and deployment time. Setting up Redis Streams can comfortably fit within the two-week limit, while Kafka would require significant ramp-up time, especially since the team has no existing experience.
2. **Operational Complexity**: Redis Streams offers a simpler operational model compared to Kafka, allowing for easier management without requiring dedicated infrastructure knowledge on the team.
3. **Latency and Throughput**: Given our current architecture, Redis can handle the expected throughput and latency requirements due to its in-memory capabilities, which aligns better with the expected 10x traffic growth.
4. **Message Retention**: Redis Streams supports configurable message retention and can maintain messages for completing the notification requirements and implementing retries.
5. **Consumer Groups**: Redis Streams enable the creation of consumer groups, allowing multiple consumers to process messages efficiently while also supporting delivery guarantees for billing-critical notifications. 
6. **Exactly-once Semantics**: While ensuring exactly-once delivery with Redis Streams may require careful design, it is achievable with proper mechanisms in place, particularly due to the current use of Redis in our infrastructure.

## Consequences
### Pros  
- Reduced operational complexity through existing knowledge of Redis.  
- Quicker implementation timeline, enabling fast delivery of value.  
- Suitable for our scaling targets with in-memory speed.  
- Supports message retention and consumer groups for improved processing.  
- Enables keeping notifications decoupled from the main application flow, improving application performance overall.  

### Cons  
- Redis Streams does not provide guaranteed exactly-once delivery like Kafka, which may require additional effort to implement in critical scenarios.
- Potential limitations in scale compared to Kafka under exceptionally high loads, though initial projections indicate that Redis should suffice for our immediate needs.
- Might miss out on some advanced stream processing features provided by Kafka.

## Alternatives Considered  
### Apache Kafka  
- **Rejection Reasons**: 
  1. Complexity: Initial setup and maintenance of Kafka presents a steeper learning curve for the team and would require significant time investment.
  2. Infrastructure Requirements: Running Kafka efficiently typically requires dedicated infrastructure management expertise, which our team currently lacks.  
  3. Long-term Costs: While Kafka can handle high throughput demands well, the added operational overhead and potential costs associated with running and maintaining it exceed the immediate needs and constraints of our project.

In conclusion, Redis Streams emerges as the optimal fit for our notification architecture due to its operational simplicity, integration speed, and alignment with the team's capabilities and project goals. It offers an effective balance against the backdrop of our operational constraints and growth expectations.