# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system, embedded synchronously within the HTTP request cycle of our Python/Flask monolith, is causing significant operational issues: request timeouts (averaging 800ms, spiking to 8s), silent failures, and cascading failures due to slow external dependencies. There are no delivery guarantees, which is critical for billing-related notifications.

We need to decouple notification processing to enable asynchronous handling, implement retry mechanisms with exponential backoff, guarantee at-least-once delivery for all notifications, and ideally achieve exactly-once delivery for billing-critical events. The new system must support 10x traffic growth without a complete re-architecture and be capable of integrating real-time WebSocket push notifications within two quarters.

Our engineering team consists of 6 people (3 senior, 3 mid-level) with no dedicated infrastructure engineer. We already utilize Redis for session management and rate limiting. The team has no prior Kafka experience. The solution must provide initial value within two weeks of setup and migration, and fit within a modest budget, precluding full-scale managed Kafka solutions like Confluent Cloud.

## Decision
We choose **Redis Streams** for the new notification subsystem.

This decision prioritizes speed of implementation, operational simplicity, and leveraging existing infrastructure and team knowledge over the potentially more robust, but significantly more complex, Apache Kafka ecosystem. Redis Streams directly addresses the immediate problems with minimal overhead.

## Consequences

**Pros of Redis Streams:**
*   **Low Operational Overhead:** Leverages our existing Redis deployment, reducing the need for new infrastructure, monitoring, and operational expertise. The team is already familiar with Redis.
*   **Fast Setup & Integration:** Given the team's existing Redis knowledge and the simplicity of Redis Streams, we can achieve initial value and decouple notifications within the two-week constraint.
*   **Good Performance for Current & Projected Scale:** Redis Streams can comfortably handle our current peak of 500 req/s and scale to 10x traffic (~5000 req/s) with proper instance sizing or clustering if needed.
*   **At-Least-Once Delivery & Consumer Groups:** Provides strong at-least-once delivery guarantees through consumer groups, which correctly track message consumption and enable distributed processing, retries, and dead-letter queue patterns.
*   **Real-time Capabilities:** Well-suited for real-time use cases, facilitating the future integration of WebSocket push notifications.
*   **Cost-Effective:** Utilizes existing infrastructure, avoiding the higher costs associated with managed Kafka services or the substantial operational costs of self-hosting Kafka.

**Cons of Redis Streams:**
*   **Exactly-Once Semantics:** Achieving true exactly-once semantics for billing notifications will require more application-level logic (e.g., idempotent consumers with transaction IDs) compared to Kafka's native transactional APIs, but this is a solvable problem.
*   **Scalability Ceiling:** While sufficient for 10x growth, Redis Streams may reach a scalability ceiling sooner than Kafka for truly massive, hyper-scale event streaming (e.g., hundreds of thousands of events per second) that is not currently anticipated.
*   **Ecosystem & Tooling:** The Redis Streams ecosystem, while growing, is less mature and comprehensive than Kafka's, potentially requiring more custom development for advanced monitoring or data processing pipelines.

## Alternatives Considered

**Apache Kafka:**
Apache Kafka was considered due to its industry-leading capabilities for high-throughput, fault-tolerant, and scalable event streaming. Its features include robust ordering guarantees, flexible message retention, advanced consumer group management, and strong native support for exactly-once semantics via transactional producers and consumers. These properties would be highly beneficial for our long-term scaling targets and critical billing notifications.

However, we rejected Kafka primarily due to its **high operational complexity** and the **lack of Kafka experience within our small engineering team**. Setting up, operating, and maintaining a production-grade Kafka cluster (which typically involves Zookeeper or KRaft) demands significant infrastructure expertise that our team of 6, without a dedicated infra engineer, does not possess. The learning curve would contradict the constraint of delivering value within two weeks of setup. Furthermore, while managed Kafka services mitigate operational burden, they can be costly, exceeding our modest budget, especially at scale. The initial investment in time and resources to get a Kafka system running reliably and for the team to gain proficiency would delay solving the immediate problem and introduce substantial risk. While Kafka offers superior "exactly-once" guarantees out-of-the-box, the trade-off in operational overhead and team learning curve is too high for our current constraints.
