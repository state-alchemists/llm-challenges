---
slug: job-queue-bugfix
---
# Job Queue Concurrency and Failure Handling Fixes

**Context:** Background job processor acting up due to duplicate processing and vanishing failures.
**Finding:** 
1. Duplicate processing was caused by a race condition in `JobQueue.dequeue` where the job status was changed to `"processing"` after yielding control with `await asyncio.sleep(0.01)`. Moving the state transition before any asynchronous yield makes it atomic under asyncio's cooperative multitasking.
2. Vanishing failures were caused by `worker.py`'s exception handler catching execution errors but failing to notify the queue. Added a call to `queue.fail` in the exception handler to trigger retry logic and transition job status appropriately.
**Source:** job_queue.py:23-28, worker.py:18-21

## Backlinks
- [Activity log (2026-07-31)](../activity-log/2026/2026-07/2026-07-31.md) — Recorded the bug fixes.
