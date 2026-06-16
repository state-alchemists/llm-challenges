# Project: SaaS Project Management Platform

## Overview
A SaaS project management platform with 85,000 MAU, ~2M tasks/month, peak 500 req/s. 

## Active Decisons & Notes
- [ADR-001 - Notification Subsystem Architecture](../index.md): We chose Redis Streams over Apache Kafka for decoupling the synchronous notifications module from the Flask HTTP request cycle.
- **Key Technical Parameters**:
  - Throughput capability: Scalable to 5,000+ req/s (10x growth targets).
  - Guarantees: At-least-once via Redis Streams consumer groups, exactly-once via Postgres unique constraints for billing events.
  - Setup timeframe: < 2 weeks.

## Backlinks
- [Projects Index](index.md)
