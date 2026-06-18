# ADR 001: Notification Architecture Decision

## Status
Proposed

## Context
The product is a SaaS project management platform with growing usage resulting in significant challenges in the notification subsystem, which currently processes notifications synchronously within the request cycle. This leads to request timeouts due to blocking notifications, silent failures in notification delivery, cascading failures impacting unrelated system features, and no robust delivery guarantees for critical notifications. The system must:

- Decouple notifications from the request cycle for asynchronous processing.
- Support retries with exponential backoff.
- Ensure at-least-once delivery for non-critical events and exactly-once delivery for billing-critical notifications.
- Scale to handle a 10x increase in traffic while maintaining system integrity.

Constraints include a small engineering team with no Kafka experience, a budget that does not permit managed solutions at scale, and a necessary focus on rapid setup and minimal operational complexity.

## Decision
After evaluating both Apache Kafka and Redis Streams, the recommendation is to implement **Redis Streams** as the notification subsystem.

**Justification:**
- **Integration with Existing Infrastructure:** The team already operates Redis in production for session management and rate limiting, which simplifies setup and minimizes training needs for the team. This allows for rapid delivery of initial value within the two-week timeline.
- **Operational Complexity:** Redis Streams has lower operational overhead compared to Kafka, especially given the team's lack of experience with Kafka. Redis is simpler to deploy and manage, which is essential given the limited engineering resources.
- **Latency and Throughput:** Redis can deliver low-latency messaging suitable for real-time requirements, while Kafka may introduce complexities in ensuring low-latency under high throughput without substantial hardware investments.
- **Exactly-Once Delivery:** Redis provides mechanisms to manage message acknowledgments and can achieve exactly-once semantics through careful state management and acknowledgment patterns, which is crucial for billing notifications.

## Consequences
### Pros:
- **Rapid Adoption:** Short setup time and familiar technology accelerates deployment.
- **Lower Complexity:** Minimal operational overhead in management and scaling.
- **Synchronous and Asynchronous Processing:** Ability to push notifications to the stream and consume them asynchronously allows for improved resilience and error handling.
- **Retention and Replay:** Notifications can be stored in Redis Streams, allowing for reprocessing in case of consumer failures.

### Cons:
- **Scaling Limitations:** Although Redis can scale, it may not handle as large a volume as Kafka in high-throughput scenarios due to single-threaded aspects. Future scaling to 10x traffic may necessitate careful architectural considerations.
- **Message Ordering:** While Redis Streams can maintain ordering within a stream, complex scenarios involving multiple consumers may require additional handling to ensure consistent ordering across distributed systems.

## Alternatives Considered
### Apache Kafka
- **Reasons for Rejection:** Kafka offers higher throughput and robust features like consumer groups and long retention times but comes with significant operational complexity and learning curves that the current team is ill-equipped to handle without dedicated personnel. The requirement for rapid migration within two weeks and low operational expenditure also makes Kafka less suitable, given the current team's constraints and existing Redis implementation.

In summary, implementing Redis Streams addresses current issues effectively while aligning with the team's capabilities and operational constraints, ensuring a manageable transition towards a more resilient notification architecture.