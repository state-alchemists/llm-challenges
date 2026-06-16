# ADR-001: Notification Architecture Decision

## Status
Proposed

## Context
The current notification subsystem in our project management platform faces several challenges: request timeouts caused by synchronous notification processing, silent failures due to unhandled errors with email providers or webhook endpoints, cascading failures impacting other features, and a lack of delivery guarantees, especially for billing-critical notifications. The goal is to create a decoupled, resilient system that can handle asynchronous processing, ensure at-least-once delivery, and meet the scaling targets without requiring extensive setup time or introducing excessive operational complexity.

## Decision
We propose to implement **Redis Streams** for the notification subsystem. **Redis Streams** offers a lightweight solution that aligns with our existing infrastructure since we are already using Redis for session storage and rate limiting. It supports the required message queue semantics, including:  
- **At-least-once delivery**: in the event of consumer failures, messages can be reprocessed.  
- **Consumer groups**: allowing multiple consumers to share the load of message processing.  
- **Operational simplicity**: easier to manage than a Kafka setup, especially given the team’s lack of Kafka experience. 

## Consequences
**Pros:**  
- **Familiarity**: Leverages existing Redis infrastructure, reducing the learning curve and operational overhead.  
- **Performance**: Lower latency in message processing due to its in-memory nature, allowing for faster notification delivery.  
- **Decoupling**: Allows for asynchronous processing which will eliminate the request timeouts currently encountered.
- **Stream Processing Model**: Efficiently handles message retention and retrieval, providing mechanisms for retries and dead-letter handling via stream processing features.

**Cons:**  
- **No Exactly-Once Semantics**: While Redis Streams provides at-least-once delivery, it cannot guarantee exactly-once delivery out of the box for billing notifications. Additional logic may be needed to handle deduplication on the consumer side.
- **Operational Limits**: Redis may face operational limits under heavy load compared to Kafka’s more robust architecture for high-throughput scenarios.

## Alternatives Considered
**Apache Kafka** was considered but rejected due to:
- **Complexity**: Kafka introduces significant operational overhead, requiring a deeper understanding of distributed system management, which our team lacks.
- **Setup Time**: The setup and migration period would likely exceed our target of 2 weeks due to the need for configurations, tooling, and infrastructure adjustments.
- **Cost**: Budget constraints make scaling a Kafka solution impractical given our current usage metrics and projections.

In conclusion, Redis Streams is the preferred solution as it meets the immediate needs with less complexity while allowing room for future adjustments as the system scales.