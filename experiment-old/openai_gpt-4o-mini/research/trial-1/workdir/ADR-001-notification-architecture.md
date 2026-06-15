# ADR 001: Notification Architecture Decision

**Status**: Proposed

## Context
The current notification module in our SaaS project management platform is tightly coupled with the HTTP request cycle, leading to significant issues during peak loads including request timeouts, silent failures, and cascading failures. Moreover, there are no delivery guarantees for critical billing notifications, which is unacceptable as we plan to grow traffic by 10x. The aim is to decouple notifications, support robust retries, and ensure that billing notifications meet exactly-once delivery semantics while being able to rapidly implement a solution within a modest budget and team capability constraints.

## Decision
The recommended choice for the notification subsystem is **Redis Streams**. This decision is driven by the following justifications:
- **Familiarity and Existing Infrastructure**: The engineering team is already proficient with Redis, utilizing it for session management and rate limiting, reducing onboarding time significantly. 
- **Low Operational Complexity**: Compared to Kafka, Redis Streams is simpler to operate and can be managed with less resource overhead, which matches our current team's capacity without needing a dedicated infrastructure engineer.
- **Delivery Guarantees**: Redis Streams supports at-least-once delivery semantics inherently. While it does not guarantee exactly-once delivery natively, we can implement a workaround using idempotent consumers or deduplication logic to meet our critical billing requirements.
- **Setup Time**: The integration of Redis Streams can be achieved within the two-week timeframe required to deliver initial value, whereas onboarding Kafka would require a longer ramp-up due to the complexity of its architecture and the team's lack of experience.

## Consequences
### Pros
- **High Throughput**: Redis Streams can handle high throughput, necessary for accommodating peak load times of up to 500 req/s and scaling accordingly.
- **Ease of Use**: With established Redis infrastructure and familiarity, our teams can quickly adapt to using Streams without extensive training or operational barriers.
- **Cost-Effective**: Leveraging existing Redis instances minimizes costs effectively as opposed to deploying Kafka which could incur higher operational costs especially for managed services.

### Cons
- **No Native Exactly-Once Semantics**: Redis Streams does not provide out-of-the-box exactly-once delivery semantics; we will need to incorporate pattern workarounds which might introduce additional development overhead.
- **Retention Management**: We will need to implement logic for message retention as the max length of streams may require active management based on application needs.

## Alternatives Considered
1. **Apache Kafka**: Kafka offers superior scalability, strong durability guarantees, and precisely-once semantics. However, its operational complexity, higher resource demands, and the learning curve for the team outweigh the benefits at this stage. Given the current team structure and expertise, the adoption of Kafka would require more than the desired setup time and resources, making it a less viable option.

In conclusion, selecting Redis Streams not only aligns with our current capabilities but also positions us well to meet the future demands of our growing user base, facilitating seamless notification management without incurring undue operational complications or delays.