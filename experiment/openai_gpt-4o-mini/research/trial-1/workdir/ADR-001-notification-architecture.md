# ADR-001: Notification Architecture

## Status
Proposed

## Context
The current architecture for our notification module sends emails and webhooks synchronously during the HTTP request cycle. This has resulted in several issues: request timeouts averaging 800ms (spiking to 8s), silent failures on notification delivery, cascading failures impacting unrelated features, and a lack of delivery guarantees for critical notifications. To address these issues, we aim to decouple the notifications from the HTTP cycle and meet requirements for async processing, retries with exponential backoff, at-least-once delivery, and exactly-once semantics for billing notifications. Our team comprises six engineers, with no Kafka experience, and we have a modest budget with an urgent need for implementation. We also need to prepare for a potential increase in traffic ten times our current volume.

## Decision
After evaluating two options—**Apache Kafka** and **Redis Streams**—I recommend implementing **Redis Streams** for the notification subsystem due to its familiarity within the team, faster implementation times, and alignment with our current infrastructure.  

### Justification:
1. **Throughput**: Both systems can handle high throughput, but Redis Streams can offer simpler scaling given our existing redis instances. 
2. **Operational Complexity**: Redis is already in use for session storage; therefore, using Redis Streams minimizes migration complexities and operational overhead. In contrast, Kafka requires significant setup and learning curve.
3. **Message Retention & Retry Handling**: Redis Streams provides built-in support for message acknowledgment, which can be configured to manage retries effectively with exponential backoff. In Kafka, achieving similar functionality would require additional setup.
4. **Exactly-once Semantics**: While Redis has made strides towards this with Streams, it might require careful implementation. However, it can meet our needs with less risk compared to Kafka, which would be more complex and may lead to challenges during implementation given our current team expertise.
5. **Setup Time**: Redis Streams can be integrated within the existing Redis setup, allowing for a maximum of two weeks to implement, whereas Kafka would likely take longer due to the team's learning curve and the need for additional infrastructure.

## Consequences
### Pros:
- **Familiarity**: Leveraging Redis means less operational complexity and easier onboarding for team members with no prior Kafka experience.
- **Speed of Implementation**: Redis Streams can be up and running in our current environment quickly, allowing us to address existing issues rapidly.
- **Cost-effective**: Redis Streams minimizes the need for additional infrastructure expenditures associated with Kafka.

### Cons:
- **Performance Limits**: Redis Streams may be less performant than Kafka in very high-throughput scenarios, particularly if task volume unexpectedly skyrockets.
- **Feature Set**: Kafka has sophisticated features such as log compaction and broader ecosystem support, which may be beneficial if requirements expand.

## Alternatives Considered
Although Kafka was initially considered due to its robust capabilities for handling high-throughput messaging and guarantees around message ordering and delivery, it was ultimately rejected because of:  
- **Learning Curve**: Our team lacks Kafka experience and the steep learning curve would conflict with our timeline.  
- **Operational Overhead**: Managing a Kafka cluster would introduce additional complexity and potential resource constraints that we cannot afford with our current engineering setup.
- **Implementation Time**: The additional time required for setup and integration of Kafka is not compatible with our need for quick resolution of the existing notification issues.