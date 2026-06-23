# ADR-001: Notification Subsystem Architecture

**Status**: Proposed

**Context**
The existing notification module, part of a Python/Flask monolith serving 85,000 monthly active users and ~2M tasks per month, handles emails and webhooks synchronously within the HTTP request cycle. This design has led to:
1.  **Request timeouts**: Latency spikes to 8 seconds during peak loads (500 req/s), blocking user requests.
2.  **Silent failures**: Notifications are dropped without retry or dead-letter queuing if external services (email provider, webhook endpoint) are unavailable.
3.  **Cascading failures**: Slow webhook endpoints have caused connection pool exhaustion and system outages.
4.  **No delivery guarantees**: Critical billing notifications lack at-least-once or exactly-once delivery guarantees.

We need to decouple notifications for async processing, implement retry mechanisms, ensure at-least-once delivery (and exactly-once for billing events), support real-time WebSocket push notifications within two quarters, and scale to 10x current traffic without re-architecture. The engineering team consists of 6 people (no dedicated infrastructure engineer), already uses Redis, has no Kafka experience, has a modest budget, and requires a solution delivering value within two weeks of setup/migration.

**Decision**
We choose **Redis Streams** for the notification subsystem.

**Justification:**
This decision is driven by the immediate constraints of team expertise, budget, and a strict 2-week "time to value" requirement. The engineering team already operates Redis in production for session management and rate limiting, providing a significant advantage in terms of familiarity, operational overhead, and learning curve.

Redis Streams allows us to rapidly implement asynchronous processing, retry mechanisms, and consumer groups to address the immediate problems of decoupling, reliability, and preventing cascading failures. Its ease of adoption within the existing infrastructure enables us to meet the aggressive timeline constraint. While achieving exactly-once semantics for billing-critical events will require careful application-level idempotence (e.g., using unique transaction IDs or message IDs to prevent reprocessing), this is a manageable architectural pattern within Redis. Furthermore, Redis's Pub/Sub capabilities, often integrated with Streams, offer a clear and familiar path for introducing real-time WebSocket push notifications. The modest budget aligns well with leveraging existing Redis infrastructure rather than incurring the significant costs of managed Kafka services or the steep operational burden of self-managing a Kafka cluster. While Kafka offers superior native scaling and transactional guarantees for complex distributed streaming, the immediate and pragmatic benefits of Redis Streams for our team and project stage outweigh Kafka's advanced capabilities at this time.

**Consequences**

**Pros:**
*   **Rapid Adoption & Time-to-Value**: Leverages existing team familiarity with Redis, significantly reducing setup time, learning curve, and enabling initial value delivery within the 2-week target.
*   **Reduced Operational Burden**: Avoids the high operational complexity and need for specialized expertise associated with self-managing Apache Kafka, freeing up valuable engineering time.
*   **Cost-Effective**: Reuses existing Redis infrastructure, avoiding the substantial costs of managed Kafka solutions.
*   **Improved System Reliability**: Effectively decouples notification processing from the HTTP request path, allowing for asynchronous retries, dead-letter queuing, and preventing cascading failures.
*   **Clear Path for Real-time**: Compatibility with Redis Pub/Sub provides a straightforward integration point for future real-time WebSocket push notifications.

**Cons:**
*   **Application-Level Exactly-Once**: Achieving robust exactly-once semantics for billing events will require careful application-level design and implementation of idempotence, as Redis Streams does not offer native transactional guarantees at the same level as Kafka.
*   **Scalability at Extreme Loads**: While Redis Streams can scale, a single Redis instance is single-threaded. Extremely high message throughput (e.g., millions per second) might eventually require sharding or a Redis Cluster, introducing additional complexity later. Kafka's distributed architecture is inherently designed for such extreme scale.
*   **Message Durability & Retention Management**: Message retention in Redis Streams requires active management to prevent memory exhaustion, and its durability profile differs from Kafka's disk-backed, append-only log. This necessitates careful planning for retention policies for critical data.
*   **Less Mature Ecosystem for Complex Stream Processing**: While Redis has a strong ecosystem, Kafka's ecosystem offers more mature and extensive tools for complex stream processing, data integration, and connectors for enterprise-level data pipelines.

**Alternatives Considered**

**Apache Kafka:**
Apache Kafka was considered but rejected primarily due to the significant challenges it presents given our team's current constraints. The primary reasons for rejection include:
*   **High Operational Complexity & Learning Curve**: None of our 6 engineers have Kafka experience. Self-managing a Kafka cluster requires dedicated expertise for setup, monitoring, tuning, and troubleshooting, which would be a substantial burden and distraction for a small team with no dedicated infrastructure engineer.
*   **Time-to-Value Constraint**: The steep learning curve and the effort required to set up and integrate Kafka effectively would almost certainly exceed the critical 2-week deadline for delivering initial value.
*   **Budgetary Constraints**: While powerful, managed Kafka services (like Confluent Cloud) are expensive and fall outside our modest budget. Self-managing would incur significant indirect costs in engineering time.
*   **Overkill for Initial Needs**: While Kafka's native support for high-throughput, distributed, and truly transactional streaming is superior, its full capabilities are beyond the immediate requirements for decoupling notifications. The complexity introduced would outweigh the benefits at this stage.

We decided against Kafka to prioritize a more pragmatic, low-overhead solution that leverages existing team knowledge and infrastructure to quickly solve the immediate problems, with the understanding that more robust streaming solutions like Kafka can be re-evaluated as our scaling needs and team capabilities evolve.
