# Title
Notification Subsystem Architecture Decision Record

# Status
Proposed

# Context
The SaaS project management platform currently handles notifications synchronously within the HTTP request cycle, leading to significant latency issues, silent failures, and hitting connection limits during peak hours. With a user base of 85,000 and a scope for growth, the notifications system must be able to support a tenfold increase in traffic without re-architecting. The goals include decoupling the notification system from the main request cycle, ensuring reliable delivery (including exactly-once semantics for billing-critical notifications), and incorporating real-time updates without excessive staff overhead.

# Decision
After evaluating both Apache Kafka and Redis Streams, we recommend adopting **Redis Streams** for our notification subsystem. The decision is driven by the following factors:
1. **Familiarity**: The engineering team already has experience with Redis, which will minimize ramp-up time and allow for faster integration.
2. **Setup Time**: Redis Streams can be integrated in less than two weeks, aligning with our project timeline requirements.
3. **Operational Complexity**: Redis is already part of our stack, lowering the need for additional operational overhead that would come with Kafka, which the team is not familiar with.
4. **Performance**: Redis Streams provides sufficient throughput and supports at-least-once delivery semantics, aligning with our requirements for billing notifications.

# Consequences
**Pros:**  
- Reduces latency by decoupling notifications from the synchronous request cycle.  
- Built-in support for message persistence and delivery guarantees.  
- Simplifies the operational aspect as it builds on existing Redis infrastructure.

**Cons:**  
- Redis Streams doesn't natively support consumer groups as robustly as Kafka, meaning higher complexity in managing multiple consumers.  
- Exactly-once delivery semantics require careful implementation and management, increasing complexity in some scenarios (though feasible).

# Alternatives Considered
1. **Apache Kafka**:  
   - Rejected due to the following reasons:  
     - The complexity and lack of familiarity with Kafka increase the risk of implementation failures within our two-week timeframe.
     - Higher operational efforts and costs, especially since we cannot adopt managed solutions.
     - While Kafka offers robust message delivery guarantees and support for large-scale architectures, it does not align with our team's current capabilities nor our modest budget constraints. 
    
2. **SQS or other messaging systems**:  
   - Although cloud-native solutions like AWS SQS could have paired well with scaling needs, they lack the real-time capabilities we require for WebSocket notifications and don't fit well into our budget or existing stack.