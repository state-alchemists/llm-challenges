# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system is synchronous, leading to request timeouts (up to 8s), silent failures, and cascading failures due to connection pool exhaustion. We need to decouple notifications from the HTTP request cycle to improve reliability and support scaling.

**Key Constraints:**
- **Team:** 6 developers, no dedicated infra engineer; zero Kafka experience.
- **Infrastructure:** Already running Redis in production for sessions/rate limiting.
- **Requirements:** 
    - At-least-once delivery for general events; exactly-once for billing-critical events.
    - Support for exponential backoff retries.
    - Ability to scale 10x (up to 5,000 req/s peak).
    - Delivery of value within 2 weeks.
    - Budget constraints preventing high-cost managed services (e.g., Confluent Cloud).

## Decision
We will use **Redis Streams** for the notification subsystem.

**Justification:**
Redis Streams provides the necessary primitives (consumer groups, message persistence, and acknowledgments) to achieve the required reliability with significantly lower operational overhead than Kafka for our current team composition.

1. **Operational Simplicity:** The team already manages Redis. Adding Streams is a configuration and code-level change, rather than deploying and managing a new, complex cluster (Zookeeper/KRaft, JVM tuning, etc.).
2. **Delivery Guarantees:** By using Consumer Groups and explicit acknowledgments (`XACK`), we achieve at-least-once delivery. Exactly-once semantics for billing events will be implemented via **idempotency keys** at the consumer level (storing processed message IDs in PostgreSQL), which is a more robust pattern than relying on broker-level transactions.
3. **Performance & Scaling:** With a peak of 500 req/s (and a 10x target of 5k req/s), Redis Streams easily handles the throughput. Redis's low latency ensures the "async" transition is nearly instantaneous.
4. **Time to Market:** Leveraging existing infrastructure allows the team to implement the producer-consumer pattern and retry logic within the 2-week window.
5. **Future Proofing:** Redis Streams' ability to handle multiple consumer groups allows us to easily add the planned WebSocket push notification service as a separate consumer without modifying the producer.

## Consequences
**Pros:**
- **Zero New Infrastructure:** No additional binaries to install or clusters to maintain.
- **Fast Deployment:** Immediate delivery of value by utilizing an existing dependency.
- **Sufficient Throughput:** More than capable of handling the 10x growth target.
- **Ordering:** Guarantees ordering per stream, which is sufficient for task updates.

**Cons:**
- **Memory Pressure:** Unlike Kafka, which persists to disk, Redis is primarily in-memory. We will need to monitor memory usage and implement strict stream capping (`XADD ... MAXLEN ~ 10000`) to prevent OOM.
- **Less Robust Ecosystem:** Kafka has a richer ecosystem for complex stream processing (Kafka Connect, KSQL), but our current requirements do not justify this complexity.

## Alternatives Considered
**Apache Kafka**
- **Why Rejected:** The "Operational Tax" is too high. Kafka requires significant expertise to manage reliably (partitioning strategy, offset management, JVM tuning). The team has zero Kafka experience and no dedicated infra engineer. Introducing Kafka would likely exceed the 2-week delivery window just for environment setup and would introduce a high risk of misconfiguration leading to production instability. While Kafka offers superior long-term retention and exactly-once semantics, the idempotency-key pattern in Redis provides sufficient correctness for our billing needs without the massive overhead.
