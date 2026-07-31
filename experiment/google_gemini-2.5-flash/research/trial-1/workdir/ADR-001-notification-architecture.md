# ADR-001: Notification Subsystem Architecture Decision

## Status
Proposed

## Context
The existing notification subsystem, part of a Python/Flask monolith, handles email and webhook dispatch synchronously within the HTTP request cycle. This architecture is currently causing significant issues: request timeouts (avg. 800ms, spikes to 8s), silent failures due to lack of retries or dead-letter queues, and cascading failures from slow external endpoints. Critical billing notifications lack delivery guarantees.

We serve 85,000 monthly active users, generating ~2M tasks per month, with peak loads of ~500 req/s. The goal is to decouple notifications, implement async processing, support retry with exponential backoff, ensure at-least-once delivery for billing events (and exactly-once where feasible), and prepare for real-time WebSocket push notifications within two quarters. The system must handle 10x traffic growth without re-architecture.

Key constraints include an engineering team of 6 (no dedicated infrastructure engineer), existing Redis usage for caching/rate limiting, no prior Kafka experience, a strict deadline of two weeks to deliver initial value, a modest budget (precluding full-scale managed Kafka), and a hard requirement for exactly-once semantics for billing-critical notifications.

## Decision
We will use **Redis Streams** for the new asynchronous notification subsystem.

This decision is primarily driven by the need for rapid time-to-value, leveraging existing infrastructure, and the team's current expertise, while still meeting the core scaling and reliability requirements. Redis is already deployed and familiar to the team, significantly reducing the operational overhead and learning curve.

Redis Streams offer durable message queues with features like consumer groups, automatic acknowledgment, and ordered processing within a stream. While Redis Streams inherently provide at-least-once delivery, achieving exactly-once semantics for billing-critical events will require careful implementation of idempotent processing and consumer-side deduplication logic (e.g., using a unique message ID stored in PostgreSQL or a dedicated Redis set). This is a manageable application-level complexity compared to the infrastructure complexity of introducing and operating Kafka from scratch.

## Consequences

### Pros
*   **Leverages Existing Infrastructure & Expertise**: Redis is already in production for other use cases, and the team is familiar with its operation. This significantly reduces the learning curve and time for deployment and initial setup.
*   **Rapid Time-to-Value**: Given the existing Redis instance and team familiarity, we can realistically achieve the "2 weeks of setup/migration work before delivering value" constraint, quickly addressing the urgent performance and reliability issues.
*   **Lower Operational Complexity**: Managing Redis Streams is less complex than operating a self-hosted Kafka cluster (which requires managing Zookeeper/Kraft, brokers, and extensive monitoring) for a team without a dedicated infrastructure engineer.
*   **Scalability for Growth**: Redis Streams can handle the initial 10x traffic growth target, supporting high throughput and concurrent consumers via consumer groups.
*   **Ordering Guarantees**: Messages within a stream are ordered, which is important for certain notification sequences.
*   **Future WebSocket Integration**: Redis's Pub/Sub capabilities can be easily integrated with the Streams for real-time WebSocket push notifications, providing a unified messaging backend.

### Cons
*   **Application-level Exactly-Once**: Achieving strict exactly-once semantics for billing notifications requires implementing idempotent consumers with explicit deduplication logic (e.g., tracking processed message IDs). This adds complexity to the application code, whereas Kafka provides stronger transactional guarantees natively.
*   **Long-term Retention & Disk Usage**: Redis Streams are primarily memory-resident. While configurable, maintaining very long retention periods for large volumes of messages might require careful memory management, persistence strategies, or potentially sharding Redis instances, which could become a scaling challenge further down the line than Kafka's disk-backed storage.
*   **Extreme Scale Limitations**: While capable of significant scale, Kafka is architected for even higher throughput and longer-term, fault-tolerant message retention at extreme scales. If traffic far exceeds the 10x target, a re-evaluation might be necessary, but this is a distant concern.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its robust features, including native support for exactly-once semantics via transactions, high throughput, and long-term message retention.

#### Reasons for Rejection
*   **High Operational Complexity**: Deploying, configuring, and maintaining a Kafka cluster (including Zookeeper/Kraft) is a significant infrastructure undertaking. This requires specialized knowledge that the current 6-person engineering team, without a dedicated infrastructure engineer and no prior Kafka experience, does not possess.
*   **Steep Learning Curve**: The team would face a substantial learning curve to understand Kafka's architecture, APIs, and operational best practices. This directly conflicts with the constraint of delivering value within two weeks.
*   **Budget Constraints**: While self-hosting Kafka is an option to manage costs, the engineering effort required for its setup and ongoing maintenance translates to significant indirect costs. Managed Kafka solutions like Confluent Cloud would likely exceed the "modest budget" at full scale.
*   **Overkill for Immediate Needs**: While Kafka offers superior long-term scalability and retention, its complexity outweighs the immediate benefits for our current stage, especially considering the time-to-value constraint. Redis Streams can adequately meet the immediate 10x scaling target with lower overhead.
