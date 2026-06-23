---
slug: concurrency-race-conditions
---
# Concurrency Race Conditions

**Context:** Multi-task concurrent checkout processing.
**Finding:** Early check-then-act stock management patterns in asynchronous flows introduce a Time-of-Check to Time-of-Use (TOCTOU) race condition. Pre-decrementing stock (reserving) before payment charging guarantees stock availability and eliminates negative stock (overselling). Releasing reserved stock immediately on payment failures ensures exact delivery matching and prevents lockups. Concurrent identical order_ids are deduplicated using in-flight and completed trackers.
**Source:** checkout.py:1-55

## Backlinks
- [HUD](../index.md)
- [Technical Index](index.md)
- [2026-06-23 log](../activity-log/2026/2026-06/2026-06-23.md) — documented bug fix activity
