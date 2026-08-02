# Title  
ADR-001: Notification Architecture Decision  

# Status  
Proposed  

# Context  
This architecture decision record evaluates options for implementing the notification subsystem in a SaaS-based project management platform. The current implementation causes significant bottlenecks due to synchronous processing of notifications, resulting in request timeouts and a lack of delivery guarantees. Key constraints include:  
- An average rate of 500 requests per second during peak hours.  
- Engineering team of 6, with limited Kafka experience.  
- Existing Redis infrastructure in production.  
- Requirement for exactly-once delivery for billing-critical notifications.  
- Setup/migration must not exceed 2 weeks.  

# Decision  
After careful consideration of our requirements and constraints, I recommend using **Redis Streams** for the notification subsystem.  

## Justification:  
1. **Familiarity and Existing Infrastructure**: The team is experienced with Redis, which will reduce the learning curve and make initial implementation faster within the specified 2-week timeframe.  
2. **Simplicity and Lower Operational Overhead**: Redis can be operated as an in-memory data structure store, while Kafka requires more complex infrastructure management and tuning, which is unsuitable given our engineering team's size and skillset.  
3. **Performance**: Redis Streams are known for high throughput, enabling efficient pub/sub mechanisms, which significantly mitigates the risk of blocking, unlike our current synchronous implementation.  
4. **Support for At-Least-Once Delivery**: Redis Streams provides a mechanism to handle retries with an automatic acknowledgment mechanism, making it feasible to implement exactly-once semantics for billing notifications using Lua scripting for operations on a stream.  
5. **Future Compatibility**: Redis allows for relatively seamless integration of real-time WebSocket notifications without requiring significant changes to the architecture.  

# Consequences  
## Pros:  
- **Asynchronous Processing**: Decoupling from the HTTP request cycle will improve response times and reduce timeouts.  
- **Delivery Guarantees**: Ability to implement retries and guarantees for billing notifications, improving overall reliability.  
- **Lower Setup Time**: Utilizing existing Redis setup and knowledge minimizes initial setup time and costs.  

## Cons:  
- **Initially Limited Scalability**: While Redis Streams handle growth well, concerns may arise as overall request volume and stream size scale dramatically (may require further considerations in the future).  
- **Only At-Least-Once Delivery**: Redis Streams require efforts to achieve exactly-once guarantees, primarily around managing acknowledgments in the delivery pipeline, making implementation more complex than for normal notifications.

# Alternatives Considered  
1. **Apache Kafka**:  
   - **Justification for Rejection**: While offering robust features such as high throughput and fault tolerance, the complexity of setting up Kafka, and the need for more operational overhead and team expertise, makes it less viable. Additionally, Kafka's focus on distributed systems and its setup requirements exceed both our team's current capabilities and the two-week migration constraint.