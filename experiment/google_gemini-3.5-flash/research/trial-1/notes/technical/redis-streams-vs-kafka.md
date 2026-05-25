---
slug: redis-streams-vs-kafka
---
# Notification Subsystem: Redis Streams vs. Apache Kafka

**Context:** Evaluated messaging backends for decoupling synchronous notification dispatch under tight team size (6 engineers) and time constraints (2-week setup/migration limit).
**Finding:** Redis Streams is selected over Apache Kafka due to its minimal operational footprint (reusing existing production Redis), sub-millisecond latencies, and support for consumer groups (`XGROUP`). Apache Kafka is rejected due to its high operational overhead, steep learning curve, and the unsuitability of its broker-level Exactly-Once Semantics (EOS) for external HTTP webhook/SMTP delivery, which requires application-level idempotency regardless.
**Source:** `ADR-001-notification-architecture.md`
