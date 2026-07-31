# Notification Subsystem Architecture Decision Record

## Status
Proposed

## Context
The SaaS project management platform currently faces significant challenges with its notifications subsystem. The existing synchronous handling of notifications has led to request timeouts, silent failures, and cascading failures during peak usage. Additionally, there are no delivery guarantees for critical billing notifications which need to be delivered exactly once. Given the team's composition (6 members, with only 3 seniors) and constraints including a modest budget and existing infrastructure utilizing Redis, we need an efficient, reliable, and scalable architecture to address these issues while anticipating a tenfold increase in traffic.

## Decision
After evaluating both **Apache Kafka** and **Redis Streams**, we recommend adopting **Redis Streams** for the notification subsystem. The justification for this decision includes:
  - **Familiarity**: The engineering team is already familiar with Redis, reducing the learning curve and minimizing setup time. Given the constraint of delivering value within two weeks, Redis Streams provides a more immediate path to implementation.
  - **Latency**: Redis Streams can offer lower latency in message processing compared to Kafka, which is vital to avoid impacting user experience.
  - **Delivery Guarantees**: While both systems can support at-least-once delivery semantics, Redis Streams can be configured to ensure exactly-once delivery for billing notifications through Lua scripting and atomic operations. This aligns with the requirement to safeguard critical events.
  - **Operational Overhead**: Managing Redis in production is less complex than Kafka, especially since the current team lacks Kafka experience. The operational complexity would likely disrupt existing workflows.

## Consequences
**Pros:**  
- Reduced operational complexity due to existing familiarity with Redis  
- Lower latency in message processing helps maintain responsiveness  
- Streamlined architecture fits well within existing infrastructure
- Redis Streams support both at-least-once and exactly-once delivery semantics, vital for billing notifications.  

**Cons:**  
- Redis Streams may have limitations in message retention and handling larger message loads compared to Kafka, which is designed for high-throughput environments. While Redis can handle significant volumes, it is essential to monitor resource usage closely as message loads increase.  
- Potential concerns regarding message replay capabilities which Kafka naturally provides, but this can be managed by implementing compensating actions within the application logic.

## Alternatives Considered
**Apache Kafka** was rejected primarily due to:
- **Learning Curve**: The team has no experience with Kafka, which would require significant time investment for effective setup, learning, and maintenance.
- **Infrastructure Overhead**: Kafka typically adds more operational complexity and may not be justified given the current resources available in the team. The larger overhead could distract from other critical development priorities and risk the implementation timeline.
- **Cost**: Although Kafka is robust, operating it at scale would exceed the budget constraints of the project, especially without a dedicated infrastructure engineer to manage it effectively.

Overall, based on the specific technical properties and the team's constraints, Redis Streams presents a more viable solution for the notification subsystem.