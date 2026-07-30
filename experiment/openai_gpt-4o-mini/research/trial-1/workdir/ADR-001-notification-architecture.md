# ADR-001: Notification Architecture

## Status
Proposed

## Context
We run a SaaS project management platform with approximately 85,000 monthly active users and peak traffic of around 500 requests per second. The current synchronous handling of notifications within the HTTP request cycle leads to request timeouts, silent failures, and cascading problems. Key requirements for the new architecture include:  
- Decoupling notifications from the HTTP request cycle for asynchronous processing.  
- Supporting retry mechanisms with exponential backoff.  
- Guaranteeing at least-once delivery for critical billing notifications and exactly-once where feasible.  
- Support for real-time WebSocket notifications within the next two quarters.  
- Scalability to accommodate a 10x increase in traffic without needing a complete re-architecture.

Given existing system constraints:  
- A modest budget and limited experience with new technologies in the team.  
- Existing use of Redis for session storage, making it a viable candidate for expansion.  

## Decision
**Option Chosen: Redis Streams**  
After evaluating both Redis Streams and Apache Kafka, we recommend adopting Redis Streams for our notification subsystem. The key reasons for this choice are:
1. **Familiarity and Existing Infrastructure**: We already utilize Redis in our infrastructure, which reduces operational overhead and learning curve for team members.
2. **Simplicity & Setup**: Redis Streams can be integrated quickly (within 2 weeks) into our existing Redis deployments without extensive migration or new infrastructure requirements.
3. **Performance**: Redis supports high throughput and low latency, ideal for our peak loads while offering predictable performance characteristics.
4. **At-Least-Once Delivery with Exactly-Once Semantics**: Redis Streams can be configured to support at-least-once delivery semantics, along with consumer groups that can be managed for scalability and reliability.

## Consequences
### Pros
- Quick to implement and leverage existing infrastructure.
- Low operational complexity with minimal additional dependencies.
- Redis Streams provide message durability and allow for managing message acknowledgments.
- The system can handle real-time delivery via WebSockets effectively due to compatibility and existing Redis usage.

### Cons
- Redis Streams does not guarantee exactly-once delivery semantics like Kafka; it can provide close approximation with careful design.
- Higher memory consumption could arise as messages grow, necessitating additional tuning of Redis settings and potential increased resource allocation.
- Limited message retention compared to Kafka unless configured for adequate persistence, which may require custom setups.

## Alternatives Considered
**Apache Kafka**  
1. **Complexity**: Requires significant learning and setup time beyond the 2-week window; the team’s current inexperience with Kafka would necessitate additional onboarding resources.
2. **Operational Overhead**: Managing Kafka's additional infrastructure involving brokers, partitions, and zookeepers would demand more from our team than we can provide without a dedicated infrastructure engineer.
3. **Cost**: Utilizing managed Kafka solutions (i.e., Confluent Cloud) remains financially impractical given our budget constraints.

In summary, while Kafka offers robust features around event streaming and exactly-once delivery, it presents challenges that outweigh its benefits given our current scale, team size, and requirements. Redis Streams provide a suitable solution within our constraints, fostering quick implementation and minimal risk as we evolve our notification architecture.