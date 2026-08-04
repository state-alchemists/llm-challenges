# ADR-001: Notification Subsystem Architecture Decision

## Status
Proposed

## Context
The existing SaaS project management platform, serving 85,000 monthly active users and handling approximately 2 million tasks per month (peaking at ~500 requests/second), relies on a Python/Flask monolith. The current notification mechanism, which sends emails and webhooks for task-related events, is synchronously coupled with the HTTP request cycle. This has led to severe issues:
- **Request timeouts**: Latency spikes (average 800ms, up to 8s during peak) due to blocking I/O.
- **Silent failures**: Notifications are dropped without retry if external services (email, webhooks) are unavailable.
- **Cascading failures**: External service slowness has caused connection pool exhaustion and system-wide outages.
- **No delivery guarantees**: Critical billing notifications lack at-least-once or exactly-once delivery.

The objective is to decouple notifications from the request cycle, implement async processing with retry logic, guarantee at-least-once delivery for billing events (exactly-once where feasible), and support future real-time WebSocket notifications. The solution must scale to 10x current traffic.

**Key Constraints:**
- **Team Size**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure engineer.
- **Existing Infrastructure**: Redis is already in production for session management and rate limiting.
- **Kafka Experience**: None within the team.
- **Time-to-Value**: Max 2 weeks setup/migration.
- **Budget**: Modest, precluding expensive managed Kafka solutions at full scale.
- **Criticality**: Exactly-once semantics for billing notifications are mandatory.

## Decision
The notification subsystem will be implemented using **Redis Streams**.

This decision is driven primarily by the project's operational constraints and the existing team's expertise. Redis is already a known quantity within the engineering team, significantly reducing the learning curve and operational overhead compared to introducing a new, complex distributed system like Kafka. The modest budget and the strict 2-week time-to-value requirement strongly favor leveraging existing infrastructure and knowledge.

Redis Streams provide robust capabilities for asynchronous messaging, including:
- **Consumer Groups**: Enables parallel consumption and distributed processing of messages, similar to Kafka.
- **At-least-once Delivery**: Guarantees that messages are processed, with explicit acknowledgment.
- **Message History/Retention**: Configurable `MAXLEN` allows retaining messages for retries and auditing, albeit typically for shorter durations than Kafka's default disk-backed storage.
- **Operational Simplicity**: As an extension of an existing Redis setup, the operational complexity and learning curve are minimal for the current team. This avoids the need for new infrastructure expertise (e.g., Zookeeper/KRaft, Kafka brokers).
- **Scalability**: While Kafka scales horizontally further, Redis Streams within a well-provisioned Redis cluster can comfortably handle the projected 10x traffic growth (up to ~5000 req/s), especially for a decoupled notification workload. Scaling Redis might involve sharding, but it's a known pattern for the team.
- **Exactly-once Semantics**: While Redis Streams primarily offer at-least-once, exactly-once semantics for critical billing notifications can be achieved at the application level through idempotent consumers and storing a unique message ID (e.g., in PostgreSQL) to prevent duplicate processing, which is a manageable engineering task given the team's Python/Flask expertise.
- **Future WebSocket Integration**: Redis Pub/Sub and Streams are frequently used for real-time applications, making it a natural fit for the planned WebSocket push notifications.

## Consequences

### Pros
- **Reduced Operational Overhead**: Leverages existing Redis infrastructure and team knowledge, minimizing setup, maintenance, and monitoring burden.
- **Faster Time-to-Value**: Can be implemented and delivering value within the 2-week constraint due to familiarity.
- **Cost-Effective**: Avoids the significant infrastructure and licensing costs associated with managed Kafka solutions.
- **Simplified Architecture**: Prevents the introduction of an entirely new distributed system and its associated complexity into a small team's stack.
- **Good Fit for Real-time**: Naturally aligns with the future requirement for WebSocket push notifications.
- **Scalable for Current Needs**: Adequately handles the projected 10x traffic increase for asynchronous notification processing.

### Cons
- **Limited Long-term Retention**: Message retention is memory-bound or relies on `MAXLEN` truncation, which is less suited for long-term historical data analysis compared to Kafka's disk-backed logs. However, notification events typically do not require indefinite retention in the stream itself.
- **Application-level Exactly-Once**: Achieving true exactly-once semantics for billing notifications requires more diligent application-level idempotent processing logic, rather than relying solely on the messaging system's native features. This adds development complexity for critical paths.
- **Vertical Scaling Limitations**: While Redis can scale horizontally via sharding, a single Redis instance has vertical scaling limits that Kafka's distributed architecture is designed to overcome more seamlessly for extreme throughput requirements beyond the current project scope.
- **Less Mature Ecosystem for Stream Processing**: While robust, the ecosystem around Redis Streams for complex stream processing (e.g., Kafka Streams, ksqlDB) is not as mature or feature-rich as Kafka's.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-leading capabilities in high-throughput, fault-tolerant, and distributed messaging, particularly its strong guarantees for ordering and exactly-once semantics.

**Reasons for Rejection:**
- **High Operational Complexity and Learning Curve**: The primary reason for rejection. The engineering team lacks Kafka experience and dedicated infrastructure engineers. Setting up, operating, and monitoring a Kafka cluster (including Zookeeper/KRaft) is a significant undertaking that would exceed the 2-week time-to-value constraint and place a heavy burden on a small team.
- **Budget Constraints**: While self-hosted Kafka is open-source, the expertise required to run it reliably in production is a "hidden cost". Managed Kafka services (like Confluent Cloud) that abstract this complexity are currently beyond the project's modest budget at full scale.
- **Overkill for Immediate Needs**: While Kafka's extreme scalability is appealing for very large enterprises, the projected 10x growth can be handled by Redis Streams without introducing the operational overhead of Kafka. The current problem is primarily about decoupling and basic reliability, not processing petabytes of data streams.
- **Slower Adoption**: The steep learning curve for a new technology and its ecosystem would significantly delay the delivery of the core notification decoupling feature, contradicting the urgent need to address request timeouts and failures.
