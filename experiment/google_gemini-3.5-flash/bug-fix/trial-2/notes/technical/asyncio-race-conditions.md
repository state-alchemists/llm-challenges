---
slug: asyncio-race-conditions
---
# Asyncio Race Conditions

**Context:** Async functions in Python yielding context at await points.
**Finding:** Any await point (like `await asyncio.sleep(...)`) inside a non-atomic read-modify-write block creates an opportunity for concurrent tasks to see stale state, leading to duplicate processing. Mutating state to lock down ownership must occur before yielding control via any `await`.
**Source:** job_queue.py:23

## Backlinks
- [Technical Index](index.md) — technical listing
- [2026-07-30 Activity Log](../activity-log/2026/2026-07/2026-07-30.md) — fix executed and verified here
