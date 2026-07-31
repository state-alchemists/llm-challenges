# ADR-001-notification-architecture: Notification Subsystem Architecture

- **Status**: Proposed

## Context

The current notification module synchronously handles email and webhook dispatch within the HTTP request cycle, leading to request timeouts, silent failures, and cascading outages. Billing-critical notifications lack delivery guarantees.

The system needs to decouple notifications, support retries with exponential backoff, guarantee at-least-once delivery for billing events (exactly-once where feasible), and prepare for real-time WebSocket push notifications within two quarters. It must scale to 10x current traffic.

Constraints include an engineering team of 6 (3 senior, 3 mid-level) with no dedicated infrastructure engineer, existing Redis deployment, no Kafka experience, a maximum of 2 weeks for initial setup/migration, and a modest budget precluding fully managed Kafka at full scale today. Maintaining exactly-once semantics for billing notifications is a hard requirement.

## Decision

We will use **Redis Streams** for the notification subsystem.

## Consequences

**Positive**:
- **Operational Simplicity**: Leverages existing Redis infrastructure and team familiarity, minimizing operational overhead, learning curve, and setup time. This directly addresses the constraint of no dedicated infrastructure engineer and the 2-week setup/migration limit.
- **Delivery Guarantees**: Redis Streams provide consumer groups, message persistence, and at-least-once delivery, which directly addresses the problem of silent failures and enables retry mechanisms. With careful consumer implementation, exactly-once processing for billing notifications is achievable through idempotent processing and explicit acknowledgment.
- **Integration Ease**: Simpler to integrate into the existing Python/Flask monolith due to existing Redis client libraries and established operational patterns.
- **Real-time Path**: Provides a clear and efficient path for future real-time WebSocket push notifications due to Redis's pub/sub capabilities and suitability for low-latency data dissemination.
- **Scalability**: Capable of handling the immediate 10x traffic growth target, with current peak loads of ~500 req/s scaling to 5,000 req/s well within Redis Streams' capabilities, especially with sharding if needed.

**Negative**:
- **Long-term Retention**: Redis Streams are primarily designed for real-time message processing rather than long-term data archival. Managing message retention beyond a few days for audit trails or historical analysis might require implementing external archiving solutions, adding minor complexity.
- **Extreme Scale Horizontal Scaling**: While suitable for 10x growth, Redis Streams may require more manual sharding and operational tuning than Kafka for throughput requirements significantly beyond the 5,000 req/s range or for extremely large numbers of distinct topics and partitions.
- **Stream Processing Limitations**: Not designed for complex, multi-stage stream transformations or event-driven microservices architectures on the scale that Kafka can support natively. This could become a limiting factor if the future roadmap includes highly complex event-stream processing beyond simple fan-out.

## Alternatives Considered

-   **Apache Kafka**: Rejected due to the significant operational complexity and steep learning curve for a small engineering team without dedicated infrastructure experience. The initial setup, configuration, and migration efforts for a Kafka cluster would likely exceed the stringent 2-week setup/migration constraint. A self-managed Kafka deployment would impose a substantial ongoing operational burden on the team, diverting resources from product development. While Kafka offers superior throughput, inherent long-term message retention, and robust capabilities for complex stream processing, these benefits are outweighed by the immediate operational challenges, team constraints, and modest budget that precludes fully managed Confluent Cloud at full scale today. The goal of exactly-once semantics is achievable with Kafka but also requires careful consumer implementation, similar to Redis Streams. The project's current scale and immediate scaling targets do not necessitate Kafka's full feature set at the cost of operational overhead.
