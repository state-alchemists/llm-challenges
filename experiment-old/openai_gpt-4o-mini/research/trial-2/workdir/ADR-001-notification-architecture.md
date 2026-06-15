# Notification Architecture Decision Record

**Status**: Proposed  

## Context  
The notifications module in our SaaS project management platform currently handles notifications synchronously within the HTTP request cycle. This approach has led to request timeouts, silent failures, cascading failures due to slow webhook endpoints, and a lack of delivery guarantees, particularly for billing-critical notifications. Given the system's current load of around 500 requests per second and projected growth, we need to decouple the notification sending from the request cycle while ensuring at-least-once delivery guarantees, ideally with exactly-once semantics for billing notifications.

## Decision  
We will adopt **Redis Streams** for the notification subsystem.  

### Justification  
1. **Existing Infrastructure**: We already run Redis in production, which reduces the setup and migration effort significantly. This allows us to get started quickly without major training or infrastructure changes.  
2. **Operational Complexity**: Given the team's current skill set, Redis Streams provides an easier operational model compared to Apache Kafka. The learning curve for Kafka is steep, especially without existing expertise in the team.
3. **Performance**: Redis Streams can achieve high throughput and low latency, which aligns with our needs to send notifications in real time. 
4. **Message Delivery Guarantees**: While Redis does not provide exactly-once semantics out of the box, it supports message acknowledgement and can be configured for at-least-once delivery. With proper handling, we can implement a reliable retry mechanism for billing notifications.
5. **Time to Implement**: Since we already use Redis, we foresee being able to implement and test the Redis Streams solution within the 2-week timeline, maintaining focus on delivering value quickly.

## Consequences  
### Pros  
- **Familiar Technology**: Utilizes existing Redis infrastructure, minimizing the need for extensive training.  
- **Quick Setup**: Can be implemented within the required timeline, enabling us to address the current frustrations with notifications rapidly.  
- **High Throughput**: Capable of handling increased traffic as we scale, which is crucial for the 10x expected growth.
- **Reduced Latency**: Moving notifications to an asynchronous model should significantly improve user experience by reducing latency.

### Cons  
- **Limited Exactly-Once Support**: Redis Streams lacks built-in support for exactly-once delivery semantics, which could complicate the handling of billing notifications unless manual mechanisms are developed.  
- **Operational Complexity with Scale**: While Redis scales easily, managing streams at scale may still require careful planning and monitoring.

## Alternatives Considered  
**Apache Kafka**:  
- **Rejection Reasons**: 
  - Requires substantial setup time beyond our 2-week constraint due to the need for a more complex infrastructure and the team's lack of experience with Kafka.  
  - Higher operational overhead and maintenance due to the additional components (like Zookeeper) typically required for Kafka setups.  
  - While Kafka excels in exactly-once semantics and durability, our existing constraints and benefits of Redis lead to prioritizing straightforward solutions given our team's current capabilities.

In conclusion, Redis Streams is chosen for this subsystem as it aligns best with our current infrastructure, team capacity, and business needs while being able to scale as our user base grows.