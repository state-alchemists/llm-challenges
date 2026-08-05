# ADR-001-notification-architecture

## Title
Notification Subsystem Architecture Decision: Apache Kafka vs. Redis Streams

## Status
Proposed

## Context
The existing notification subsystem in our SaaS project management platform is synchronous, tightly coupled with the HTTP request cycle. This has led to severe performance bottlenecks (request timeouts, latency spikes up to 8 seconds), silent failures of critical notifications due to lack of retry mechanisms, and cascading failures from slow external webhook endpoints. We currently serve 85,000 monthly active users with ~2M tasks created per month and peak traffic of ~500 req/s.

Our scaling targets require decoupling notifications for asynchronous processing, implementing robust retry with exponential backoff, guaranteeing at-least-once delivery for all notifications, and ideally exactly-once semantics for billing-critical events. The new architecture must also support 10x traffic growth and integrate real-time WebSocket push notifications within two quarters.

Key constraints influencing this decision are:
- A small engineering team of 6 (3 senior, 3 mid-level) with no dedicated infrastructure engineer.
- Existing operational experience with Redis for session management and rate limiting.
- No prior team experience with Apache Kafka.
- A strict timeline of no more than 2 weeks for initial setup/migration to deliver value.
- A modest budget, precluding expensive managed solutions like Confluent Cloud for full-scale deployment.
- A non-negotiable requirement for exactly-once semantics for billing-critical notifications.

## Decision
We choose **Redis Streams** for the notification subsystem.

While Apache Kafka offers superior scalability, advanced features, and stronger ecosystem integration for large-scale data streaming, it introduces significant operational complexity and a steep learning curve for our small team with no prior Kafka experience. The 2-week timeline for initial value delivery and modest budget further disfavor Kafka, as self-hosting would require substantial upfront investment in expertise and operational tooling, which our team lacks. Managed Kafka solutions, while simplifying operations, exceed our budget at the necessary scale.

Redis Streams, conversely, leverages our team's existing operational knowledge of Redis. It provides core messaging capabilities—append-only log, consumer groups, automatic message acknowledgment, and persistent message history—that directly address our immediate problems:
- **Asynchronous processing**: Messages can be pushed to a stream and processed by workers, decoupling from the HTTP request cycle.
- **Retry mechanisms**: Consumer groups natively support explicit acknowledgment and pending entry lists (PEL), allowing for easy implementation of retries for unacknowledged messages.
- **At-least-once delivery**: Achievable with consumer groups and proper acknowledgment.
- **Exactly-once semantics**: While not native to Redis Streams in the same way Kafka provides it with transactions, it is achievable for billing notifications by implementing idempotent consumers at the application level, combined with unique message IDs and tracking processed messages in our PostgreSQL database. This approach aligns with patterns we can build on top of Redis without introducing a new, complex distributed transaction system.
- **Scalability**: Redis Streams can handle our current peak of 500 req/s and scale to 10x traffic growth with proper sharding or clustering, especially given its lighter footprint compared to Kafka.
- **Real-time push notifications**: Redis's Pub/Sub feature can complement Streams for real-time WebSocket pushes, providing a unified messaging solution within a familiar ecosystem.
- **Operational Complexity**: Significantly lower than Kafka, as we already operate Redis in production. Initial setup and integration will be much faster, aligning with our 2-week delivery constraint.

## Consequences

### Positive
- **Reduced operational overhead**: Leverages existing Redis infrastructure and team expertise, minimizing the learning curve and operational burden.
- **Faster time to value**: The initial setup and migration are estimated to be within the 2-week constraint, allowing for rapid deployment of the asynchronous notification system.
- **Improved system responsiveness**: Decoupling notifications from the request cycle will drastically reduce HTTP latency and eliminate timeouts.
- **Enhanced reliability**: Built-in retry mechanisms and message persistence mitigate silent failures.
- **Cost-effective**: Avoids the high costs associated with managed Kafka services or the significant engineering investment required for self-hosting and managing Kafka clusters.
- **Unified messaging solution**: Potential to use Redis Pub/Sub for real-time WebSocket notifications alongside Streams, consolidating messaging concerns within one technology.

### Negative
- **Lower raw throughput compared to Kafka**: While sufficient for our current and 10x projected scale, Redis Streams may not match Kafka's extreme throughput capabilities for future, much larger data streaming needs. This is a trade-off accepted for operational simplicity.
- **More manual effort for complex use cases**: Implementing complex data transformations, stream processing, or event sourcing might require more application-level code compared to Kafka Streams or ksqlDB.
- **Exactly-once semantics requires application-level care**: Achieving true exactly-once delivery for billing notifications demands careful implementation of idempotent consumers and state tracking in our application, rather than relying on a native distributed transaction feature from the messaging system itself.
- **Limited ecosystem for stream processing**: The Redis ecosystem for advanced stream processing is less mature and extensive than Kafka's.

## Alternatives Considered

### Apache Kafka
**Reason for Rejection**:
Apache Kafka is a powerful distributed streaming platform renowned for high-throughput, fault-tolerance, and strong ordering guarantees. It natively supports consumer groups, robust message retention policies, and provides strong guarantees for at-least-once and even exactly-once semantics through transactional producers and consumers. Its ecosystem is vast, with tools for stream processing (Kafka Streams, ksqlDB), integration (Kafka Connect), and monitoring.

However, Kafka's operational complexity is significant. It requires a dedicated Zookeeper ensemble, and managing a Kafka cluster effectively demands specialized infrastructure expertise for deployment, monitoring, scaling, and troubleshooting. Our engineering team of 6 has no dedicated infrastructure engineer and no prior Kafka experience. Introducing Kafka would necessitate a substantial learning curve, extensive setup time, and a significant operational burden that directly conflicts with our constraint of delivering value within 2 weeks and our modest budget (precluding managed Kafka services). While its long-term scalability and feature set are superior, the immediate costs in terms of time, expertise, and operational overhead make it an impractical choice for our current team and constraints. The need for exactly-once semantics for billing notifications could be met with Kafka's transactional features, but the overall complexity outweighs this benefit given our other constraints and the possibility of achieving it with Redis Streams via idempotent consumers.
