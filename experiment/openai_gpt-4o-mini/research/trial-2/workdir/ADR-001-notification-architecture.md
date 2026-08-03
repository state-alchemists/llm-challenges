# ADR-001: Notification Architecture

## Status 
Proposed

## Context  
The notifications module in our SaaS project management platform currently handles emails and webhooks synchronously during HTTP requests. As user traffic has increased, this has resulted in multiple issues: 
1. Request timeouts, averaging 800 ms and spiking to 8 seconds during peak usage.
2. Silent failures when external services are down, leading to missing notifications and no retry capabilities.
3. Cascading failures affecting unrelated features due to blocking behavior and connection pool exhaustion.
4. Lack of delivery guarantees for critical notifications, such as billing-related events.

To address these issues, we need to decouple the notification sending from the HTTP request cycle, support asynchronous processing and retries, and maintain delivery guarantees, especially for billing events.

## Decision 
We choose **Redis Streams** for the notification subsystem. This decision is based on our existing use case, the team's familiarity with Redis, and the architecture's constraints:
- **Throughput**: Redis is capable of handling high-throughput requirements efficiently and can manage many connections concurrently.
- **Ordering Guarantees**: Redis Streams maintain order within individual streams, which is beneficial for task-related notifications.
- **Message Retention**: While Redis Streams allows configuration for message retention, it can be tuned to meet our requirements for retries, ensuring that messages persist as needed.
- **Consumer Groups**: Redis Streams supports consumer groups, enabling us to build a scalable architecture for processing notifications asynchronously, improving fault tolerance.
- **Operational Complexity**: Since we already utilize Redis for session management, integrating Streams presents a lower operational overhead compared to introducing Apache Kafka, for which the team lacks experience.

Additionally, it aligns better with our timeline of not exceeding 2 weeks for setup and migration work.

## Consequences 
**Pros**:
- Fast integration leveraging existing Redis infrastructure; no need for extensive onboarding on a new technology.
- Sufficient throughput for projected growth, with capabilities for simultaneous processing without blocking.
- Less operational burden since Redis is already managed, limiting the need for complex deployment narratives.
- Direct compatibility with existing systems for real-time push notifications using WebSockets.

**Cons**:
- Redis Streams do not have the same level of durability as Kafka in very high-throughput scenarios. 
- Lack of built-in support for exactly-once semantics may require additional logic to handle such cases.
- Limited features compared to Kafka, which is optimized for complex event processing and scalable message handling.

## Alternatives Considered  
**Apache Kafka**: 
- Rejected due to the team's lack of experience, leading to potential delays in adoption and implementation. 
- Requires more time for setup and operational know-how, exceeding our 2-week constraint.  
- While Kafka provides stronger durability and exactly-once delivery semantics, the operational complexity and cost of a managed solution are beyond our current budget.

Thus, Redis Streams are a more suitable choice for our notification architecture, balancing our current infrastructure needs with future growth potential.