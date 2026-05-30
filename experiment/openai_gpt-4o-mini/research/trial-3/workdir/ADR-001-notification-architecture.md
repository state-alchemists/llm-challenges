# Notification Subsystem Architecture Decision Record (ADR)

## Title
Notification Subsystem Architecture Decisions for the Notifier System

## Status
Proposed

## Context
The notification module in our SaaS project management platform is currently blocking the HTTP request cycle. Recent growth has resulted in request timeouts, silent failures, and cascading issues due to slow webhook processing. Critical billing notifications lack delivery guarantees. Our objectives include decoupling message processing to support asynchronous execution, reliably delivering important notifications, and being prepared for significant traffic increases (up to 10x).

## Decision
We will implement **Redis Streams** for the notification subsystem. This decision is motivated by:
- Pre-existing infrastructure with Redis allows rapid deployment and reduced complexity.
- Redis Streams supports message durability and management of message delivery through consumer groups and acknowledgment patterns, meeting our exacting requirements for notification reliability.
- We have limited experience with Docker and managed solutions like Confluent Kafka, assessing the learning curve for our team versus the existing Redis stack.

## Consequences
### Pros
- **Ease of Implementation**: Leveraging existing Redis clusters allows us to implement Redis Streams swiftly with minimal changes to the codebase (less than two weeks).
- **High Throughput**: Redis is known for low latency, providing high throughput with sub-millisecond performance even under heavy load.
- **Consumer Groups**: Offers a simple mechanism for handling message acknowledgments and ensuring messages can be processed reliably by multiple consumers, allowing for scaling according to demand.
- **Simplified Operations**: Redis generally requires less operational overhead than Kafka, particularly given the team's current skills and available resources.  

### Cons
- **Retention Limits**: Redis Streams’ message retention features depend on configured policies. If not appropriately managed, this could lead to the deletion of important notifications if they are not consumed promptly.
- **No Built-in Exactly-Once Semantics**: While messages can be acknowledged, managing exactly-once delivery semantics requires well-designed patterns in handling consumed messages.
- **Complexity for Large Scale**: As the application scales, managing Redis Streams may become curent with its own unique operational challenges, specifically at extremely high throughput levels beyond Redis's typical use case.

## Alternatives Considered
### Kafka
- **Reason for Rejection**:
  - **Learning Curve**: The team lacks Kafka experience, making the ramp-up time notable. Adding Kafka would exceed the desired two-week minimal setup time before delivering value.
  - **Operational Complexity**: Kafka generally has higher operational overhead and requires more architectural adjustments compared to Redis Streams.
  - **Costs**: Full-scale deployment of Kafka (especially a managed solution like Confluent Cloud) may be budget-prohibitive given our current financial constraints.
  - **Performance**: While Kafka excels at durability and scalability, our current needs around throughput and simplicity make Redis Streams a more fitting choice.
  
Given these factors, Redis Streams presents a more viable solution aligned with the team’s constraints, existing infrastructure, and immediate needs.