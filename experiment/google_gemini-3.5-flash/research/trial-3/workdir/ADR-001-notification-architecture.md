# ADR-001: Selection of Redis Streams for the Notification Subsystem

## Status
Proposed

## Context
We operate a SaaS project management platform that currently supports 85,000 monthly active users (MAU), handles approximately 2 million task creations per month, and experiences peak traffic of ~500 requests per second (req/s) during business hours. 

Currently, our notifications module (responsible for sending emails and webhooks when tasks are updated, assigned, or completed) runs synchronously within the HTTP request-response cycle of our 50k-line Python/Flask monolith. This synchronous design has introduced several critical problems in production:
1. **Request Timeouts**: Sending notifications synchronously blocks HTTP worker threads, leading to an average latency of 800ms that spikes up to 8s during peak hours.
2. **Silent Failures**: Down downstream email providers or third-party webhook endpoints cause notifications to be silently dropped, as there is no retry mechanism or dead-letter queue (DLQ).
3. **Cascading Failures**: Unstable, slow external webhooks have exhausted our PostgreSQL database connection pool twice this year, resulting in cascading downtime across unrelated platform features.
4. **No Delivery Guarantees**: Billing-critical notifications (such as "trial expired" and "payment failed") have no delivery guarantees, introducing high business and operational risk.

### Scaling Target & Objectives
To support a 10x traffic growth target (up to 5,000 req/s peak) without requiring an immediate re-architecture of the database or web layer, we must transition to an asynchronous notification subsystem that achieves the following goals:
- Decouple notification dispatching from the HTTP request cycle.
- Support robust message retries with exponential backoff.
- Guarantee at-least-once delivery for general notifications, and exactly-once processing for billing events.
- Enable real-time WebSocket push notifications within 2 quarters.

### Constraints
- **Engineering Team**: 6 engineers (3 senior, 3 mid-level) with no dedicated infrastructure or DevOps engineer.
- **Setup Time**: The solution must be production-ready and deliver business value in under 2 weeks.
- **Budget**: Modest. We cannot afford the licensing or cloud hosting costs of expensive managed solutions such as Confluent Cloud at our expected scale.
- **Technical Stack**: The team already runs and operates Redis in production (primarily for session storage and rate limiting).
- **Expertise**: The team has zero operational or development experience with Apache Kafka.

---

## Decision
We choose **Redis Streams** as the underlying message broker for our new asynchronous notification subsystem.

### Justification

1. **Alignment with Team Constraints and Operational Complexity**: 
   Since we already run Redis in production for session management and rate limiting, adopting Redis Streams introduces **zero new infrastructure**. For a team of 6 product-focused engineers with no dedicated DevOps specialist, self-managing an Apache Kafka cluster (with its dependencies on ZooKeeper or KRaft, JVM tuning, disk monitoring, and partition rebalancing) represents a severe, unsustainable operational burden. Managing Redis is already an established competency on the team, allowing us to deploy and deliver value comfortably within our 2-week deadline.
   
2. **Performance and High Throughput**:
   Our 10x scaling target requires handling up to 5,000 req/s. As an in-memory database, Redis can easily achieve 50,000 to 100,000 operations per second on a single modest instance. Redis Streams handles append (`XADD`) and read (`XREADGROUP`/`XACK`) operations with extremely low latency (sub-millisecond), ensuring our target throughput is supported with negligible resource overhead.

3. **Robust Consumer Group Native Features**:
   Redis Streams provides built-in consumer group support (via `XREADGROUP`) that matches our functional requirements. It natively tracks message delivery states via the Pending Entries List (PEL). If a worker process fails mid-execution, we can detect timed-out messages using `XPENDING` and claim them using `XCLAIM`, guaranteeing at-least-once delivery for all notification events.

4. **Guaranteed Exactly-Once Semantics (EOS) via PostgreSQL transactions**:
   While Redis Streams does not natively support distributed transactions for end-to-end exactly-once delivery across network boundaries, we can achieve **exactly-once processing** by leveraging our existing PostgreSQL database. 
   When processing a billing-critical notification, the consumer worker will insert the unique Redis Stream message ID into a PostgreSQL `processed_notifications` table (enforced by a `UNIQUE` constraint) within the same ACID transaction that performs the business operation (e.g., updating subscription state or sending notifications). If a network failure prevents the consumer from acknowledging the message via `XACK`, a retry will occur; however, the subsequent Postgres transaction will fail on the duplicate message ID constraint, rolling back the transaction and ensuring exactly-once processing.

---

## Consequences

### Pros (Benefits)
- **Zero Additional Infrastructure & Licensing Costs**: Leverages our existing Redis deployment without adding any monthly cloud spend or external managed service fees.
- **Rapid Implementation**: The team can build, test, and deploy the producer and consumer workers using the familiar `redis-py` library within a few days, satisfying our < 2 weeks constraint.
- **Ultra-low Latency**: Messages are published and read in-memory, providing sub-millisecond queuing latencies compared to disk-bound brokers.
- **Flexible Consumer Scaling**: Unlike Kafka, where scaling consumer groups is strictly capped by the number of partitions, Redis Streams allows us to scale our worker processes up and down dynamically based on queue depth without partition-level limitations.

### Cons (Drawbacks & Mitigations)
- **In-Memory Retention Constraints**: Redis stores stream data entirely in RAM, making long-term message storage cost-prohibitive.
  *Mitigation*: We will strictly bound our streams using the `MAXLEN ~ 10000` option to keep a rolling buffer of active/recent notifications. Once processed and acknowledged, notifications are pruned. If we require historical audit logs, we will persist notification delivery records in our durable PostgreSQL database.
- **Data Loss Risk on Redis Crash**: Because Redis is in-memory, a node crash before writing to disk could result in message loss depending on the persistence configuration.
  *Mitigation*: We will configure Redis AOF (Append Only File) persistence with `appendfsync everysec`. For critical billing notifications, we will write a pending notification record to PostgreSQL *before* publishing to Redis, ensuring that even in the event of an un-replicated Redis crash, we can reconstruct and republish billing notifications.
- **No Built-in DLQ or Exponential Backoff**: Redis Streams does not have automatic dead-letter queue (DLQ) routing or retry timers.
  *Mitigation*: We will implement application-level retry logic. If a message exceeds 5 processing attempts (inspected using `XPENDING` metrics), our consumer worker will publish the message to a designated `notifications-dlq` stream, acknowledge the original message (`XACK`), and log a high-priority alert for manual intervention.

---

## Alternatives Considered

### Apache Kafka
We thoroughly evaluated Apache Kafka and rejected it for the following reasons:
- **Prohibitive Operational Complexity**: Operating a production-grade, highly available Kafka cluster requires a dedicated infrastructure engineer. Dealing with partition counts, replication factors, broker configurations, JVM tuning, and disk alerts would deplete our small 6-person team's capacity.
- **Too Slow to Value**: Provisioning Kafka, implementing secure network access, training the team, and restructuring our code to use Kafka client libraries would easily exceed our strict 2-week setup/migration constraint.
- **High Financial Cost**: To ensure high availability, self-hosted Kafka requires at least 3 brokers and 3 ZooKeeper/KRaft nodes, adding significant server costs. Managed services (e.g., Confluent Cloud) are too expensive and exceed our modest budget constraints.
- **Over-engineered**: Kafka is built to handle millions of events per second with high data retention. For our 500 req/s peak (and 10x target of 5,000 req/s), using Kafka is massive over-engineering that introduces unnecessary architectural complexity.

We would have chosen Apache Kafka only if our scale requirements exceeded 50,000 req/s, if we had a dedicated platform engineer, or if we had a pre-allocated budget to afford managed enterprise streaming plans.
