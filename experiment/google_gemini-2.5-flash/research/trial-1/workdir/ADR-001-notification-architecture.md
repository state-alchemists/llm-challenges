# ADR-001: Notification Subsystem Architecture

- **Status**: Proposed

## Context

The existing notification module within our Python/Flask monolith synchronously handles email and webhook dispatches, leading to critical performance and reliability issues. These include request timeouts (up to 8 seconds during peak), silent failures for undeliverable notifications, cascading failures due to slow external endpoints, and a complete lack of delivery guarantees.

We need to decouple notifications from the HTTP request cycle, implement retry mechanisms with exponential backoff, guarantee at-least-once delivery for billing events, and achieve exactly-once semantics where feasible. The system must also support real-time WebSocket push notifications within two quarters and scale to 10x current traffic.

Constraints include an engineering team of 6 with no dedicated infrastructure engineer, existing Redis usage, no prior Kafka experience, a maximum of 2 weeks for initial setup/migration, and a modest budget precluding managed Confluent Cloud at full scale.

## Decision

We will implement the notification subsystem using **Redis Streams**. This decision prioritizes rapid implementation, leverages existing infrastructure and team familiarity with Redis, and addresses the immediate scaling and reliability requirements within the specified constraints.

## Consequences

**Positive**:
- **Rapid Implementation**: Leverages existing Redis infrastructure, reducing setup and operational overhead. The team's existing Redis knowledge shortens the learning curve.
- **Simplified Operations**: Redis Streams are part of the existing Redis deployment, avoiding the introduction of an entirely new, complex distributed system (Kafka) with its own operational burden.
- **At-Least-Once Delivery**: Redis Streams inherently provide at-least-once delivery guarantees through consumer groups, which is sufficient for billing events.
- **Exactly-Once Feasibility**: While true global exactly-once semantics are challenging with any distributed system without significant application-level effort, Redis Streams' consumer group semantics combined with idempotent processing can approximate exactly-once semantics for critical messages like billing notifications.
- **Real-time Capabilities**: Redis is well-suited for real-time applications, aligning with the future requirement for WebSocket push notifications.
- **Scalability**: Redis Streams can handle the projected 10x traffic growth without immediate re-architecture for our specific notification use case, providing sufficient throughput for ~20M tasks per month.

**Negative**:
- **Limited Long-term Retention**: Redis Streams are not designed for indefinite message retention, which might require a separate archival strategy if audit logs spanning months or years are needed directly from the stream.
- **Scaling Complexity (Horizontal)**: While vertical scaling of Redis is straightforward, horizontal scaling of Redis Streams for extreme throughput (beyond 10x the current load) can be more complex than Kafka, potentially requiring sharding at the application level.
- **Tooling and Ecosystem**: The Redis Streams ecosystem, while growing, is less mature and comprehensive than Kafka's, which might necessitate more custom development for advanced monitoring or integration patterns.
- **No Native Exactly-Once Semantics**: While feasible with application-level idempotency, Redis Streams do not provide native transactional exactly-once semantics across producers and consumers like Kafka's transaction API.

## Alternatives Considered

- **Apache Kafka**:
  - **Why rejected**: Kafka offers superior long-term message retention, higher throughput for extreme scale, and a mature ecosystem with extensive tooling and strong exactly-once guarantees via its transaction API. However, introducing Kafka would impose significant operational complexity on a small engineering team with no prior Kafka experience. The setup and migration would likely exceed the 2-week constraint, and the budget precludes managed Confluent Cloud at full scale. Given the current team's bandwidth and immediate needs, the operational overhead and learning curve of Kafka outweigh its technical advantages for this phase. While Kafka is a powerful solution for high-volume, long-retention messaging, it's an over-engineering for our current constraints and scaling target.
