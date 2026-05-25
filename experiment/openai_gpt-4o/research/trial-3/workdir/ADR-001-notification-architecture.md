# ADR-001: Notification Subsystem Architecture

## Status
Proposed

## Context
The current notification system for our SaaS project management platform is embedded within the HTTP request cycle, causing significant latency and reliability issues. These include request timeouts, silent failures, cascading failures affecting unrelated features, and lack of delivery guarantees for critical notifications. To address these, we aim to decouple notification delivery using an asynchronous processing model, support retry mechanisms, and ensure both at-least-once and exactly-once delivery semantics where necessary. This needs to be done within the constraints of our small engineering team and limited budget.

## Decision
We choose to implement the notification subsystem using **Redis Streams**. Redis is already part of our existing architecture, minimizing additional setup complexity. Redis Streams offers at-least-once delivery semantics, which we can use for general notification tasks. For billing-critical notifications that require exactly-once semantics, additional application logic will be implemented. The familiarity with Redis among our team will enable faster deployment and iteration cycles compared to Kafka, for which we currently have no expertise.

## Consequences
### Pros
- **Reduced Complexity**: Leveraging an existing component (Redis) simplifies integration.
- **Rapid Deployment**: Can be set up and operational within the required two-week timeframe.
- **Team Familiarity**: Lowers the learning curve, accelerating development and troubleshooting.
- **Cost-effective**: Avoids additional expenses by not introducing a new major dependency.

### Cons
- **Exactly-once Semantics**: Achieving exactly-once delivery will require additional application-level handling, as Redis Streams does not natively support this out-of-the-box.
- **Scalability Limits**: Redis Streams may require additional scaling strategies (e.g., Redis Cluster) to handle extreme loads efficiently.

## Alternatives Considered
### Apache Kafka
Kafka was considered due to its strong durability and message retention capabilities, along with built-in support for exactly-once semantics. However, its integration poses several challenges:
- **Technical Expertise**: The team lacks experience with Kafka, increasing the risk and time required for successful deployment.
- **Operational Overhead**: Without a managed solution, maintaining on-premises Kafka introduces significant complexity.
- **Budget Constraints**: Managed Kafka solutions are not financially viable given our current budget constraints.
- **Setup Time**: Implementing and tuning a Kafka cluster would likely exceed the two-week setup limit before value delivery.