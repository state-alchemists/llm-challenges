# HUD - LLM Session Journal Index

## Active Constraints & Preferences
- Focus on technical precision and minimal operational complexity.
- Preference for leveraging existing proven infrastructure (e.g. Redis, PostgreSQL) rather than introducing heavyweight distributed systems (e.g. Kafka) for small/mid-sized teams.

## Recent Decisions & Insights
- **ADR-001: Notification Subsystem Decision**: Chosen Redis Streams over Apache Kafka for SaaS notification system. Tapped existing Redis instance to stay within tight timeline (2 weeks), budget, and team size (6 people) constraints. Exactly-once semantics achieved via Postgres-backed idempotent consumers.
  - Path: `workdir/ADR-001-notification-architecture.md`

## Project Index
- [SaaS Project Management Platform](projects/saas-platform.md)

## Activity Log
- [Activity Log Index](activity-log/index.md)

## Backlinks
*None*
