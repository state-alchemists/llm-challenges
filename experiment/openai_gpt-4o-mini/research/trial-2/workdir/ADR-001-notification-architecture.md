# ADR-001: Notification Architecture

## Status
Proposed

## Context
The notification subsystem is critical for sending emails and webhooks when tasks are updated, assigned, or completed. Currently, notifications are handled synchronously within the HTTP request cycle, leading to:
1. Request timeouts due to blocking on notification delivery, with average latencies of 800ms and spikes up to 8s during peak hours.
2. Silent failures where notifications are dropped without retries or dead-letter queues.
3. Cascading failures affecting unrelated features due to slow webhook endpoints.
4. No delivery guarantees for billing-critical notifications, compromising business integrity.

To address these issues, the team needs a solution that decouples notification processing from HTTP request flows, supports asynchronous processing, retry strategies, and guarantees at-least-once delivery, especially for billing events. The scaling target anticipates handling a 10x increase in traffic and ensuring real-time WebSocket push notifications.

## Decision
We recommend using **Redis Streams** for the notification subsystem. This choice primarily stems from the following:
- **Existing Infrastructure**: The team currently operates Redis in a production environment, minimizing setup complexity. No significant learning curve is necessary for the team, compared to adopting Kafka, for which the team lacks experience.
- **Operational Complexity**: Redis Streams simplifies operational overhead since the team already possesses Redis expertise without the need for additional infrastructure or complex deployment strategies.
- **Cost**: Given budget constraints, Redis is a more economical choice as it does not require scaling to a fully managed Kafka solution.

Redis Streams offers robust features adequate for the current and anticipated demands of the notifications subsystem. 

## Consequences
**Pros:**
1. **Immediate Integration**: Leveraging existing Redis infrastructure reduces implementational timelines and complexity.
2. **Message Ordering**: Redis Streams maintain order within streams, which is important for maintaining the sequence of notifications sent.
3. **Consumer Groups**: Built-in support for consumer groups allows scalability to manage multiple receivers for notifications.
4. **Task Retry Mechanism**: Support for retry logic and message acknowledgment reduces silent failures.

**Cons:**
1. **Exactly-Once Semantics**: Redis provides support for at-least-once delivery semantics, but achieving exactly-once delivery is more complex compared to Kafka’s capabilities.
2. **Data Retention**: Managing message retention for long-lived messages may require additional considerations and planning, as Redis generally operates as an in-memory datastore.

## Alternatives Considered
**Apache Kafka** was considered as a potential choice for this architecture. However, it was rejected based on the following reasons:
- **Steeper Learning Curve**: The current team has no existing experience with Kafka, which adds to operational complexity and learning overhead.
- **Setup Time**: Given the requirement to deliver value within two weeks, Kafka would likely necessitate more extensive setup and integration compared to Redis.
- **Cost**: A full-scale Kafka deployment, particularly a managed option, exceeds budget constraints.

In summary, Redis Streams is favored for its alignment with current resources, immediate integration potential, and cost-effectiveness, making it a suitable choice for future-proofing the notification subsystem.