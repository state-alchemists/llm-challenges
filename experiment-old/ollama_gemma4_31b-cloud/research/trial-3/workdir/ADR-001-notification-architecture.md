# ADR-001: Notification Subsystem Architecture

## Title
Selection of Message Broker for Notification Subsystem

## Status
Proposed

## Context
The current notification system operates synchronously within the HTTP request cycle, leading to request timeouts (spikes up to 8s), cascading failures via connection pool exhaustion, and a lack of delivery guarantees. We need to decouple these processes to support retries with exponential backoff and a scaling target of 10x current traffic (~5,000 req/s peak).

**Key Constraints:**
- **Team:** 6 engineers (no dedicated infra/DevOps). 
- **Infrastructure:** Already running Redis; zero Kafka experience.
- **Timeline:** Maximum 2-week setup/migration window.
- **Business Requirement:** Exactly-once semantics for billing-critical notifications.
- **Future Proofing:** Support for real-time WebSocket push notifications within 6 months.

## Decision
We will use **Redis Streams** as the foundation for the notification subsystem.

**Justification:**
Given the team size and current infrastructure, the operational overhead of Kafka is prohibitive. Redis Streams provides the necessary primitives (consumer groups, message persistence, and offset tracking) to meet our requirements without introducing a new, complex piece of infrastructure.

- **Operational Complexity:** Since we already run Redis in production for sessions and rate limiting, there is zero new infrastructure to deploy, monitor, or secure. 
- **Throughput & Latency:** At 5,000 req/s peak, Redis Streams handles the load with sub-millisecond latency, far exceeding our requirements.
- **Consumer Groups:** Redis Streams supports consumer groups, allowing us to distribute notification processing (emails vs. webhooks) across multiple workers.
- **Delivery Guarantees:** By utilizing the `XACK` (acknowledgment) mechanism and maintaining pending entries (PEL), we can implement at-least-once delivery and build a retry loop with exponential backoff.
- **Exactly-Once Semantics:** While Redis Streams provides at-least-once delivery, we will achieve "exactly-once" for billing events by implementing **idempotent consumers** at the application level (using a `processed_notification_ids` table in PostgreSQL), which is the industry-standard approach regardless of the broker.

## Consequences
**Pros:**
- **Rapid Deployment:** Can be implemented within the 2-week window using existing Redis clusters.
- **Low Overhead:** No need for Zookeeper or Kafka Connect; the 6-person team can maintain the system without specialized infra knowledge.
- **WebSocket Ready:** Redis is the ideal backbone for the upcoming WebSocket push notifications (via Pub/Sub or Streams), ensuring a unified tech stack for real-time features.
- **Cost Efficient:** No additional costs for managed Kafka services.

**Cons:**
- **Memory Limitations:** Unlike Kafka’s disk-based retention, Redis is primarily in-memory. We must implement strict `MAXLEN` capping on streams to prevent OOM (Out of Memory) errors.
- **Persistence Risk:** While AOF provides durability, it is not as robust as Kafka's distributed commit log. However, for our scale and use case, this is an acceptable trade-off.

## Alternatives Considered
**Apache Kafka**
Kafka was rejected due to the extreme "operational tax" it would impose on a 6-person team.
- **Complexity:** The team has zero Kafka experience. Learning and managing Kafka (clusters, partitions, offsets) would exceed the 2-week delivery window.
- **Infrastructure Burden:** Running a production-ready Kafka cluster requires significant tuning and monitoring that we currently cannot support without a dedicated infra engineer.
- **Overkill:** Kafka's strength is massive-scale data streaming (millions of events/sec). Our 10x growth target is still well within the capabilities of a properly configured Redis Streams setup.
