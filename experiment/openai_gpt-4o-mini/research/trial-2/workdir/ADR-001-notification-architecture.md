# ADR 001: Notification Architecture

## Status
Proposed

## Context
The current notifications system in our SaaS project management platform is synchronous, leading to significant request timeouts (up to 8 seconds during peak loads), silent failures, and cascading issues affecting the overall reliability of the application. We need to implement a new notification subsystem that can handle 10x traffic growth while maintaining functionality, ensuring delivery guarantees, and allowing for real-time updates via WebSocket. The engineering team is composed of 6 members with no dedicated infrastructure engineer and limited experience with Apache Kafka.

## Decision
We will implement **Redis Streams** as the notification subsystem due to its compatibility with our existing infrastructure, ease of development, and ability to meet critical delivery guarantees. Redis Streams offers out-of-the-box support for consumer groups, simplified deployment, and integrations with our current Redis setup, making it a timely and cost-effective solution.

## Consequences
### Pros:
- **Familiarity with Redis**: Since we already use Redis for session and rate limiting, the team will face a shorter learning curve, enabling quicker implementation.
- **Low operational complexity**: Redis is easy to operate, especially for a small team without a dedicated infrastructure engineer. The existing Redis infrastructure requires minimal changes to integrate Streams.
- **Consumer Groups**: Redis Streams supports multiple consumers, allowing us to handle different notification types independently, leading to a more scalable architecture.
- **Exactly-once Semantics**: Ensure that billing-critical notifications are delivered with exactly-once semantics using Redis transactions (MULTI/EXEC) combined with consumer acknowledgment features.
  
### Cons:
- **Durability**: While Redis can provide durability through persistence, it may not match the durability guarantees offered by Kafka, where messages are replicated across multiple nodes. Careful configuration will be needed to ensure data is not lost, especially for billing notifications.
- **Scaling Limitations**: Although Redis can handle high throughput, it may eventually become a bottleneck at extreme peak loads compared to a distributed system like Kafka.

## Alternatives Considered 
### Apache Kafka
We rejected Kafka primarily due to the following reasons:
- **Complexity and Learning Curve**: The team lacks Kafka experience, and adopting it would require an extensive learning period, likely exceeding the 2-week setup constraint.
- **Operational Overhead**: Kafka introduces significant operational complexity, including running multiple brokers, Zookeeper management, and ensuring fault tolerance, which may overwhelm our team given current staffing constraints.
- **Cost**: Deploying Kafka in a self-managed environment would still incur costs and long-term maintenance efforts, especially if we scale up and require a more complex setup.

In summary, after weighing the requirements and challenges, Redis Streams is the more pragmatic choice for our notification subsystem at this stage.