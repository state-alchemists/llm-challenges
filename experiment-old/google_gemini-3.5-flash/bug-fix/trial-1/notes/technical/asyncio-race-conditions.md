---
slug: asyncio-race-conditions
---
# Asyncio Race Conditions and Task Failure Propagation

**Context:** Applies when implementing multi-worker consumer patterns in Python asyncio.
**Finding:** In an asynchronous context, cooperative multitasking means context switches only occur at `await` points. Setting state variables *before* any `await` (yield) point is critical to guarantee atomic check-and-set operations without requiring complex lock primitives. Additionally, workers must explicitly catch exceptions and propagate failures back to the queue coordinator to prevent silent job drops (vanishing failures).
**Source:** job_queue.py:22-29, worker.py:16-22

## Backlinks
- [Activity log entry for 2026-05-30](../activity-log/2026/2026-05/2026-05-30.md) — Recorded the fix for job duplication and vanishing failures
