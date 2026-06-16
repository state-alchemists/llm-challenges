---
slug: notifier-subsystem-broker-decision
---
# Choice of Redis Streams for Notifier Subsystem

**Context:** Decoupling a synchronous Python/Flask project management platform notification system to support 10x scale and preventtimeouts/failures.
**Finding:** Redis Streams is the selected broker for the notification subsystem. It meets all technical requirements (throughput up to 5k req/s, ordering, horizontal scaling via consumer groups, PEL retry mechanisms) with minimal operational complexity (0 new infra) and within the 2-week delivery timeline.
**Source:** [ADR-001-notification-architecture.md](../../workdir/ADR-001-notification-architecture.md)

## Backlinks
- [Projects Index](index.md) — index listing
- [Root Index](../index.md) — HUD listing
- [2026-06-16 Activity Log](../activity-log/2026/2026-06/2026-06-16.md) — decision made and logged
