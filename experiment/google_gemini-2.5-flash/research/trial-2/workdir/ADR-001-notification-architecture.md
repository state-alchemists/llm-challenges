---
Title: ADR-001 Notification Subsystem Architecture
Status: Proposed
Context: The existing synchronous notification module, responsible for sending emails and webhooks for task updates, is causing critical performance and reliability issues. These include request timeouts (spiking to 8s), silent failures due to lack of retries, cascading failures from slow external endpoints, and no delivery guarantees for billing-critical events.

The system needs to be decoupled, support async processing, include retry with exponential backoff, guarantee at-least-once delivery for billing events, and eventually support real-time WebSocket push notifications. Future traffic growth of 10x must be accommodated.

Key constraints are a small engineering team (6 people, no dedicated infrastructure), existing Redis in production, no Kafka experience, a maximum of two weeks for initial setup/migration to deliver value, a modest budget (precluding managed Confluent Cloud at full scale), and a strict requirement for exactly-once semantics for billing notifications.

Decision: We will implement the asynchronous notification subsystem using **Redis Streams**. This decision is primarily driven by the team's existing operational experience with Redis, the modest budget, and the tight two-week deadline for delivering initial value. While Apache Kafka offers a more robust platform for extreme scale and provides stronger native support for exactly-once semantics with Kafka Transactions, the immediate operational overhead and steep learning curve for a team without prior Kafka experience would significantly delay or derail the project.

Redis Streams, leveraging our existing Redis infrastructure, allows for rapid prototyping and deployment. At-least-once delivery is inherently supported through consumer groups. Exactly-once semantics for billing-critical notifications will be achieved through a combination of Redis Streams consumer groups, application-level idempotency checks (e.g., using a unique identifier for each billing event and checking a processed set before acting), and robust transaction management within the notification processing worker.

Consequences:
Pros:
- **Reduced Operational Complexity**: Leverages existing Redis deployment and team familiarity, minimizing the learning curve and operational overhead compared to a new Kafka cluster.
- **Rapid Development**: The team's existing Redis knowledge and the simpler API of Redis Streams will allow for faster initial implementation and delivery of value within the two-week constraint.
- **Cost-Effective**: Avoids the significant infrastructure and licensing costs associated with managed Kafka solutions (like Confluent Cloud) at full scale, aligning with our modest budget. Self-managed Kafka would incur high operational costs for a small team.
- **Scalability for Mid-Tier**: Redis Streams can handle the projected 10x traffic growth (5000 req/s) for notifications, especially with appropriate partitioning and worker scaling, and can serve as a solid foundation for WebSocket push notifications.
- **At-Least-Once Delivery**: Redis Streams Consumer Groups naturally provide at-least-once delivery by tracking consumer progress and requiring explicit acknowledgement.

Cons:
- **Manual Exactly-Once Semantics**: Achieving true exactly-once semantics for billing will require more diligent application-level design and implementation (idempotency keys, transaction handling) compared to Kafka's native transaction API. This adds development complexity.
- **Message Retention Management**: Redis Streams require explicit trimming or management of message retention, which needs to be carefully configured to avoid unbounded memory usage.
- **Lower Throughput Ceiling**: While sufficient for current and projected needs, Redis Streams generally have a lower absolute throughput ceiling and fewer advanced features (e.g., KSQL, Kafka Connect) compared to Kafka for extreme data streaming scenarios.
- **Potential for Redis Resource Contention**: If not properly designed, heavy Redis Streams usage could contend with existing Redis roles (session management, rate limiting), requiring careful monitoring and potentially separate Redis instances.

Alternatives Considered:
**Apache Kafka:**
Rejected due to:
- **High Operational Complexity**: Setting up and maintaining a Kafka cluster (especially self-managed) requires significant expertise in distributed systems, zookeepers/brokers, and monitoring, which our small team lacks. This would heavily violate the "no dedicated infrastructure engineer" constraint.
- **Steep Learning Curve**: The entire team would need to acquire new skills, delaying initial delivery beyond the two-week setup/migration constraint.
- **Budget Constraints**: Managed Kafka solutions at scale are expensive, and self-managing would lead to high operational costs in terms of engineering time.
- **Overkill for Initial Scope**: While Kafka's capabilities (e.g., KSQL, complex stream processing) are powerful, they are beyond the immediate requirements for a notification subsystem and would introduce unnecessary complexity at this stage.