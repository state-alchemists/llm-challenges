# ADR-001: Notification Subsystem Architecture Decision

## Status  
Proposed

## Context  
The notification subsystem is a critical component of our SaaS project management platform that currently handles email and webhook notifications synchronously. As user demand has grown, this has resulted in request timeouts, silent failures, and cascading failures affecting other features. We need to decouple notifications from the HTTP request cycle to improve response times, ensure delivery, and handle future traffic growth. Additionally, guarantees on notifications regarding billing events are vital, requiring an evaluation of different messaging systems that can meet our scaling targets and constraints.

### Current Constraints:  
- Team: 6 engineers (3 seniors, 3 mid-level) without Kafka expertise  
- Existing use of Redis for session storage and rate limiting  
- Must not require more than 2 weeks of setup/migration work  
- Budget constraints, avoiding costs associated with managed Kafka services  
- Need for exactly-once semantics for billing notifications

## Decision  
After evaluating both Apache Kafka and Redis Streams for the notification subsystem, we propose implementing **Redis Streams** as the messaging architecture. 

### Justification:
1. **Familiarity and Reduced Complexity**: Since our team already uses Redis, adopting Redis Streams minimizes the learning curve and simplifies operational overhead while allowing for quick integration.
2. **Performance**: Redis Streams provides low-latency data processing and can handle the current traffic load efficiently. With its high throughput capabilities (up to millions of messages per second), it can scale with usage growth.
3. **Message Retention and Delivery Guarantees**: Redis Streams allow for at-least-once message delivery and are simple to implement with mechanisms for handling failed notifications through acknowledgment and reprocessing.
4. **Operational Simplicity**: Setting up Redis Streams is straightforward for our team, and Redis is already in our AWS infrastructure, avoiding the extra operational complexity that Kafka would introduce.

## Consequences  
### Pros:
- Immediate integration leveraging existing Redis knowledge without extensive training.
- High throughput and low latencies suitable for our average traffic and growth predictions.
- Built-in support for message acknowledgments and retries, enhancing reliability with minimal code changes.
- Familiarity with existing Redis tooling will ease operational challenges.

### Cons:
- Redis Streams lacks some of the advanced features that Kafka offers, such as multi-consumer groups and partitioning at native scale, which could limit scaling options in the future.
- Message retention can be configured, but long-term storage strategies might require additional configurations or external systems.

## Alternatives Considered  
### 1. Apache Kafka  
- **Rejection Reasons**: While Kafka provides strong features such as durable message retention, precisely-once semantics, and high consumer scalability, it also introduces significant operational complexity and requires experience we currently lack. The team would need a substantial amount of time to ramp up on setting it up, which goes against our two-week migration constraint. Additionally, Kafka's operational overhead without a dedicated infrastructure engineer could lead to challenges in management and monitoring.

### 2. Alternatives to Redis Streams
- **RabbitMQ** and other similar systems could be considered, but they too would prolong the migration period, introduce new complexities, and require additional knowledge that the team lacks. Compared to Redis Streams, they fall short in terms of integration speed and familiarity.

---  
In summary, implementing Redis Streams provides a balance between immediate value and future flexibility, ensuring that the notification subsystem meets its current and foreseeable requirements.