# Notification Architecture Decision Record (ADR)

## Status
Proposed

## Context
The notifications module for our SaaS project management platform is currently designed to handle notifications synchronously, leading to several issues as the user base has grown:
1. **Request timeouts**: Notifications block the HTTP request cycle, with average latency hitting 800ms and spikes to 8s during peak hours.
2. **Silent failures**: The current setup does not retry failed notifications, causing critical messages to be lost.
3. **Cascading failures**: Slow webhook endpoints can exhaust the connection pool, impacting unrelated functionality.
4. **No delivery guarantees**: Especially critical are billing notifications, which need to be delivered at least once, and ideally exactly once.

To address these problems, we aim to decouple the notification system from the request cycle, introduce retry mechanisms, and handle up to 10x our current traffic without significant re-architecture.

## Decision
After evaluating both **Apache Kafka** and **Redis Streams**, we recommend adopting **Redis Streams** for the notification subsystem. This choice aligns well with our current infrastructure and operational constraints:
- **Familiarity with Redis**: The engineering team already operates Redis in production for session storage, which reduces onboarding time and operational complexity.
- **Minimal setup and migration time**: Redis Streams can be integrated within the 2-week limit specified without needing extensive setup compared to Kafka.

## Consequences
### Pros of Choosing Redis Streams:
1. **Ease of Integration**: Given the current usage of Redis, integrating Redis Streams will require less training and adjustments for the team.
2. **Operational Simplicity**: Redis operates with lower operational overhead for our team; fewer components to manage translates to smoother day-to-day operations.
3. **At-least-once delivery guarantees**: We can implement consumer groups and acknowledgments to ensure that notifications are delivered reliably.
4. **Throughput**: Redis can handle a high volume of messages (up to millions of messages per second) if configured appropriately.
5. **Supports real-time WebSocket notifications**: The existing Redis infrastructure can readily accommodate WebSocket pushes.

### Cons of Choosing Redis Streams:
1. **Message Retention**: Redis does not retain messages indefinitely, which may pose challenges if a prolonged failure is encountered. However, we can configure TTL (time-to-live) settings wisely to manage retention effectively.
2. **Limited Complicated Use Cases**: For complex streaming data use cases or very high throughput, Kafka is usually more advantageous. However, Kafka's complexity feels unjustified for our current needs.

## Alternatives Considered
1. **Apache Kafka**:
   - **Justification for Rejection**: While Kafka is an excellent solution for high throughput and message retention, the lack of in-house expertise presents a significant barrier. Existing operational complexity would demand more resources and longer onboarding, which contradicts our objective of delivering a solution quickly.
   - **Cost and Infrastructure**: Our budget constraints also make Kafka a less favorable option, especially since managed services can be costly at our scale.

In conclusion, adopting Redis Streams for the notification subsystem aligns with our needs for reliability, operational simplicity, and quick deployment within our current constraints.