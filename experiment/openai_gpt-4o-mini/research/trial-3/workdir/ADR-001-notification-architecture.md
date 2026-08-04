# Notification Architecture Decision Record (ADR-001)

**Status:** Proposed

## Context

Our SaaS project management platform has seen significant growth, with 85,000 monthly active users generating approximately 2 million tasks and reaching peak traffic of around 500 requests per second. Currently, the notifications module handles email and webhook notifications synchronously within the HTTP request cycle. This design leads to request timeouts, silent failures, and cascading failures during peak load. Given the evolving needs, we are looking to decouple this module for async processing with guaranteed delivery, especially for billing-critical notifications requiring exactly-once semantics.

Key constraints include:
- Existing team composition lacks experience with Kafka.
- We must leverage current infrastructure (Redis) where possible.
- Must deliver value quickly within a timeline of two weeks.
- Limited budget prevents the use of managed solutions like Confluent Cloud.
- Retain exactly-once delivery semantics.

## Decision

We have decided to implement **Redis Streams** for the notification subsystem.

### Justification:
1. **Familiarity**: The team is already experienced with Redis due to its current use for session and rate-limiting purposes, which minimizes the onboarding time and complexity.
2. **Operational Complexity**: Redis Streams is easier to set up and manage compared to Kafka, fitting our requirement for limited setup time (within 2 weeks).
3. **Message Retention and Consumer Groups**: While both Kafka and Redis Streams offer message retention capabilities, the simplicity of Redis Streams allows for straightforward use of consumer groups to handle message processing. Kafka, while more scalable for larger volumes, introduces unnecessary complexity given our current scale and team size.
4. **Throughput**: Redis, in general, provides low latencies and decent throughput, making it suitable for our notification requirements, especially given that we are not scaling to massive traffic in the immediate future. Redis Streams can handle hundreds of thousands of notifications per second at low latency levels.
5. **Delivery Guarantees**: Redis Streams offers at-least-once delivery semantics out of the box. We can implement self-managed retry logic with exponential backoff in our application code for finer control of the flow.

## Consequences

### Pros:
- **Quick Setup**: Can be implemented within the existing infrastructure within the two-week timeframe.
- **Reduced Latency**: Asynchronous processing reduces request timeouts significantly.
- **Operational Simplicity**: Less complexity in operational overhead compared to Kafka.
- **Improved Reliability**: Capable of implementing a robust retry mechanism and tracking failures more effectively.

### Cons:
- **Scalability**: While Redis can handle our needs now, it may not handle massive flows (e.g., millions of messages) as efficiently as Kafka could in the long run.
- **Exactly-Once Semantics**: Achieving exactly-once delivery may require more effort and design decisions in code compared to Kafka, which is designed for this with its transactional support.

## Alternatives Considered

1. **Apache Kafka**: 
   - Rejected due to the team's lack of experience, which would hamper timely value delivery. Kafka's operational overhead and complexity also exceed our immediate needs and constraints, particularly regarding setup time and budget.

In conclusion, choosing Redis Streams not only aligns with our team skills but also meets our immediate architectural requirements effectively, ensuring a reliable and efficient notification subsystem as we scale.