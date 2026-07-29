---
slug: python-asyncio-locking
---
# Python Asyncio Concurrency & Lock Pattern

**Context:** Managing concurrent shared resource modification in python's `asyncio`.
**Finding:** Even though python's asyncio runs on a single thread and context switches only occur at `await` boundaries, actions involving sleeps/awaits are not safe. Using an explicit `asyncio.Lock()` to serialize checks and mutations prevents race conditions.
**Source:** inventory.py:10-25

## Backlinks
- [HUD](../index.md) — referenced as recent insight
- [Technical Index](index.md) — technical topic index
- [2026-07-29 Activity Log](../activity-log/2026/2026-07/2026-07-29.md) — pattern used to resolve race conditions
