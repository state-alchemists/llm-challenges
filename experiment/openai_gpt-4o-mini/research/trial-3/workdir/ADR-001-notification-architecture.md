# ADR-001: Notification Architecture Decision

**Status**: Proposed

## Context

The organization runs a SaaS project management platform with approximately 85,000 monthly active users and peak traffic of about 500 requests per second. The current notification system is synchronous, leading to significant issues such as request timeouts, silent failures, and cascading failures impacting unrelated features. As the need for decoupled, reliable notifications grows, a new architecture must support:

1. Asynchronous processing of notifications
2. Retry mechanisms with exponential backoff
3. At-least-once delivery for billing notifications, with a preference for exactly-once where feasible
4. Scalable to handle an expected 10x traffic growth without major re-architecting
5. Maintainable given the current team composition of 6 engineers, with limited infrastructure expertise

The infrastructure already includes Redis, while Kafka is unfamiliar to the team. The budget for third-party managed services like Confluent Cloud is also limited.

## Decision

After evaluating the options, we recommend **Redis Streams** as the solution for the notification subsystem.

### Justification

1. **Familiarity**: The team is already experienced with Redis, which reduces onboarding time and operational risk.
2. **Implementation Speed**: Redis Streams can be implemented within the two-week timeframe, enabling immediate value delivery.
3. **Simplicity**: Redis operates well in our existing architecture, avoiding the overhead of managing a new technology like Kafka.
4. **Performance**: Redis Streams can efficiently handle high-throughput scenarios while meeting the required response time constraints.

## Consequences

### Pros:
- **Speed of Implementation**: Leveraging existing Redis infrastructure allows near-instant setup and immediate integration into the application.
- **Operational Simplicity**: Redis is simpler to operate compared to Kafka, reducing the complexity for a small team with limited infrastructure experience.
- **Retention and Streams**: Redis Streams supports message retention and can implement consumer groups, making it easier to manage notifications over time.

### Cons:
- **Delivery Guarantees**: While Redis Streams can provide at-least-once delivery, implementing exactly-once semantics may require more intricate handling, potentially complicating development.
- **Scaling Limits**: While Redis is fast, it may not naturally scale as well as Kafka in extremely high throughput scenarios.

## Alternatives Considered

1. **Apache Kafka**: 
   - **Rejected Due to Learning Curve**: Given that the team lacks experience with Kafka, the required learning curve and operational overhead (setting up, maintaining clusters, managing consumers, etc.) are significant drawbacks. 
   - **Operational Complexity**: Kafka introduces additional complexity that our team may not be able to handle given the size and current capabilities.
   - **Cost Concerns**: Managed solutions for Kafka, such as Confluent, are outside the budget, leaving self-hosting as the only option.

2. **Other Messaging Systems**:
   - Alternatives like RabbitMQ were not considered as they introduce similar complexities to Kafka and do not provide significant advantages over the chosen option.