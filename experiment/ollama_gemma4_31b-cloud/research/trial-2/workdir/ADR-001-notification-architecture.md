# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system operates synchronously within the HTTP request cycle, leading to high latency (up to 8s spikes), silent failures during third-party outages, and cascading failures due to connection pool exhaustion. 

We must decouple notifications to support async processing, exponential backoff retries, and a scaling target of 10x current traffic (~5,000 req/s peak). Specifically, billing-critical notifications require "exactly-once" delivery semantics to prevent duplicate charges or missed expiration alerts.

Constraints:
- Team: 6 engineers (no dedicated infra/DevOps).
- Experience: Zero Kafka experience; existing production Redis instance.
- Timeline: Delivery of value within 2 weeks.
- Budget: Modest; cannot support high-cost managed Kafka services.

## Decision
We will use **Redis Streams** as the foundation for the notification subsystem.

**Justification:**
1. **Operational Simplicity:** We already run Redis in production. Adding Streams requires no new infrastructure, no new JVM tuning, and no new monitoring stacks, meeting the <2 week delivery constraint.
2. **Performance:** At 5,000 req/s (10x target), Redis Streams easily handles the throughput with sub-millisecond latency, which is sufficient for our needs without the overhead of Kafka.
3. **Consumer Groups:** Redis Streams provides consumer group support (similar to Kafka), allowing us to distribute notification processing across multiple workers and track offsets.
4. **Reliability:** By using the `XACK` (acknowledge) pattern and `XPENDING` inspections, we can implement at-least-once delivery and a Dead Letter Queue (DLQ) for failed webhooks.
5. **Exactly-Once Semantics:** Since Redis is already used for session/rate-limiting, we will implement exactly-once delivery for billing events using a **distributed idempotent key** pattern (combining the event ID with a Redis SETNX/TTL check) at the consumer level.

## Consequences
**Pros:**
- **Zero Infrastructure Overhead:** No new servers or clusters to manage.
- **Low Cognitive Load:** The team can leverage existing Redis knowledge.
- **Fast Time-to-Market:** Implementation can begin immediately using existing libraries.
- **Resource Efficiency:** Low memory and CPU footprint compared to a Kafka cluster.

**Cons:**
- **Retention Limits:** Unlike Kafka's disk-based retention, Redis is primarily in-memory. We must implement aggressive `XTRIM` policies to prevent memory exhaustion.
- **Persistence Trade-off:** While AOF/RDB provide durability, Redis is not as fundamentally durable as Kafka's distributed commit log in the event of total cluster failure.
- **Ecosystem:** Fewer high-level tooling options for stream monitoring compared to the Kafka ecosystem (e.g., Kafka Connect).

## Alternatives Considered
**Apache Kafka**
Rejected for the following reasons:
- **Operational Complexity:** Kafka requires Zookeeper (or KRaft) and significant JVM tuning. With no dedicated infra engineer and a team of 6, the "operational tax" is too high.
- **Implementation Timeline:** Setting up a production-ready, HA Kafka cluster and integrating it into the Python/Flask monolith would exceed the 2-week delivery window.
- **Cost:** Managed options (Confluent) are outside the current budget, and self-hosting is too resource-intensive for the current scale.
- **Overkill:** Kafka is designed for massive scale (millions of events/sec). Our 10x target (5k req/s) is well within the capabilities of a well-configured Redis instance.
