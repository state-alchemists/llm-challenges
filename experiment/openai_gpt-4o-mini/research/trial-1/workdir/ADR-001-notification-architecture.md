# ADR 001: Notification Architecture

**Status:** Proposed  

**Context:**  
The current notification system for our SaaS project management platform processes notifications synchronously, leading to significant performance issues, including timeouts and cascading failures. With growing user numbers (85,000 monthly active users) and the need to scale to handle 10x traffic growth, we must decouple notification handling from the HTTP request cycle. Our requirements are to support asynchronous processing, ensure at-least-once delivery for all notifications, and maintain exactly-once semantics for billing-critical notifications. Given our engineering team's size and experience limitations, our solution must be implementable within two weeks and fit a modest budget.

**Decision:**  
We choose **Redis Streams** as the notification subsystem's backbone. This decision is based on the following justifications:
- **Familiarity:** Since Redis is already in production for session management, the learning curve for Redis Streams will be shallower compared to Kafka.
- **Simplicity:** Redis Streams provide a straightforward implementation with built-in support for message delivery guarantees, stream management, and consumer groups without the operational complexity of maintaining a Kafka cluster.
- **Exactly-once semantics:** Utilizing Redis Streams along with Lua scripting or careful application logic allows us to implement exactly-once delivery for billing notifications, which is a crucial requirement.

**Consequences:**  
- **Pros:**  
  - **Lower operational overhead:** With our current Redis infrastructure, we can leverage existing resources and knowledge, minimizing the need for additional engineering resources.
  - **Faster setup time:** Redis Streams can be integrated quickly, allowing us to deliver immediate value within our two-week timeline.
  - **Built-in persistence and consumer support:** Redis Streams have in-memory speed with optional persistence, ensuring durable message storage and facilitating scaling.

- **Cons:**  
  - **Scaling limits:** As traffic grows, we may have to consider the limitations of Redis Streams compared to the distributed nature of Kafka, particularly regarding partitioning and throughput.
  - **Potential for message loss:** Although we can achieve exactly-once semantics, it requires careful handling, which may introduce complexity in ensuring that all edge cases are covered, especially under failures.

**Alternatives Considered:**  
1. **Apache Kafka**: While Kafka offers robust scaling and throughput benefits, and is the gold standard for messaging systems, it comes with substantial operational complexity and a steeper learning curve for our team. Given that we have no prior experience with Kafka and the crucial time constraints, it would not be feasible to adopt Kafka effectively within the next two weeks. Additionally, the ongoing maintenance and resource requirements might exceed our modest budget and team capacity.

2. **Continuation of the current system**: While we could maintain the existing synchronous approach, it would exacerbate the current issues of timeouts and delivery failures, ultimately crippling our growth potential and affecting customer experience.

By selecting Redis Streams, we gain a manageable, scalable solution that meets our immediate needs and can evolve in the future as our architecture expands.