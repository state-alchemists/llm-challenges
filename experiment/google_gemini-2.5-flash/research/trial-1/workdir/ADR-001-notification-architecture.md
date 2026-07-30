# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The existing notification module, part of a Python/Flask monolith, handles emails and webhooks synchronously within the HTTP request cycle. This design has led to several critical issues: request timeouts (latency spikes to 8s), silent failures (no retry/dead-letter queue), cascading failures due to slow webhook endpoints exhausting connection pools, and a lack of delivery guarantees for billing-critical notifications (e.g., "trial expired", "payment failed").

The goal is to decouple notification processing from the main request flow, enabling asynchronous processing, supporting retry with exponential backoff, guaranteeing at-least-once delivery for general notifications, and achieving exactly-once delivery for billing events where feasible. The new system must also support real-time WebSocket push notifications within two quarters and scale to 10x current traffic (5000 req/s peak) without significant re-architecture.

Key constraints include:
- A small engineering team (6 people, no dedicated infrastructure engineer).
- Existing Redis infrastructure used for session storage and rate limiting.
- No prior team experience with Kafka.
- A strict timeline of less than two weeks for initial setup and value delivery.
- A modest budget, precluding managed Kafka services like Confluent Cloud at full scale.
- The critical requirement for exactly-once semantics for billing notifications.

## Decision
We choose **Redis Streams** as the foundation for the new notification subsystem.

While Kafka offers superior capabilities for high-throughput, fault-tolerant distributed logging and stream processing, the immediate constraints around team experience, operational complexity, budget, and rapid time-to-value strongly favor Redis Streams. The existing Redis infrastructure reduces setup overhead, and the simpler operational model aligns with our small team lacking a dedicated infrastructure engineer. Redis Streams provides the core features required: durable messaging, consumer groups for scaling, and mechanisms to support at-least-once and even exactly-once processing (via consumer group ACKing and idempotent processing within the application). For the current scale and projected 10x growth, Redis Streams is capable of handling the required throughput and message retention (configurable on a per-stream basis).

The two-week setup/migration constraint is a major factor; integrating Kafka would require a steeper learning curve for the team and significantly more initial setup, potentially delaying critical improvements to system stability. The "modest budget" further pushes away from self-hosting a Kafka cluster without dedicated ops or paying for expensive managed services upfront.

## Consequences

### Pros
*   **Reduced Operational Complexity:** Leveraging existing Redis instances simplifies infrastructure management. The team is already familiar with Redis, lowering the learning curve and operational burden.
*   **Faster Time-to-Value:** Minimal setup and integration time, adhering to the < 2-week constraint, allows for rapid deployment of the asynchronous notification system and immediate relief from current bottlenecks.
*   **Cost-Effective:** Avoids the significant infrastructure and operational costs associated with deploying and maintaining a Kafka cluster, especially given the budget constraints and lack of dedicated SRE.
*   **Sufficient Feature Set for Current Needs:** Redis Streams provides durable messaging, ordered delivery within a stream, consumer groups for load balancing and parallel processing, and message acknowledgment, enabling at-least-once delivery. With careful application design (idempotent consumers), exactly-once semantics for billing events can be achieved.
*   **Real-time Capabilities:** Redis's in-memory nature and pub/sub capabilities make it a natural fit for future real-time WebSocket push notifications, simplifying the integration of that feature within the next two quarters.

### Cons
*   **Limited Scalability for Extreme Throughput:** While capable of handling 10x current traffic (5000 req/s) with a well-configured Redis cluster, Kafka generally offers higher sustained throughput and lower latency for extremely large-scale, high-volume streaming data scenarios beyond our current 10x target.
*   **More Manual Effort for Advanced Features:** Implementing robust dead-letter queues, advanced message transformation, or complex stream processing pipelines may require more custom application logic compared to Kafka's ecosystem (Kafka Streams, KSQL DB).
*   **Durability Management:** Redis Streams relies on RDB snapshots or AOF persistence for durability. While robust, it requires careful configuration and monitoring to ensure data safety, especially compared to Kafka's default distributed log architecture.
*   **Monitoring and Tooling Maturity:** While Redis has excellent monitoring, the ecosystem for Redis Streams-specific monitoring and operational tooling is less mature and comprehensive than Kafka's.

## Alternatives Considered

### Apache Kafka
Kafka was considered for its industry-leading capabilities in distributed streaming platforms. It excels in:
*   **High Throughput & Scalability:** Designed for extremely high message volumes and can easily handle the projected 10x traffic and beyond, with excellent horizontal scalability.
*   **Robust Delivery Guarantees:** Provides strong at-least-once and exactly-once semantics across distributed consumers and producers, critical for billing events.
*   **Message Retention & Durability:** Offers configurable, long-term message retention and a highly durable, fault-tolerant distributed log architecture.
*   **Rich Ecosystem:** A mature ecosystem with Kafka Streams for stream processing, connectors, and extensive monitoring tools.

However, Kafka was rejected primarily due to:
*   **High Operational Complexity:** Operating and maintaining a Kafka cluster (even a small one) requires significant expertise in distributed systems, zookeepers (for older versions), brokers, and partitions. Our team lacks a dedicated infrastructure engineer and Kafka experience.
*   **Steeper Learning Curve:** The team would require substantial time to learn Kafka's concepts, deployment, and operational best practices, violating the < 2 weeks setup/migration constraint.
*   **Budget Constraints:** Managed Kafka services are expensive, and self-hosting without dedicated ops staff poses a significant risk and cost in terms of potential outages and maintenance.
*   **Initial Setup Time:** The initial setup and integration would likely exceed the two-week target, delaying critical system stability improvements.

While Kafka remains a strong candidate for future, larger-scale needs, the immediate constraints make Redis Streams a more pragmatic and achievable solution for the current phase.
