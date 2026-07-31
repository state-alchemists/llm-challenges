---
slug: job-queue-bugfix
---
# Job Queue Concurrency & Exception Bugs Fixed

**Context:** The background job processor had duplicate processing and vanishing failures.
**Finding:**
1. In `job_queue.py`, `dequeue()` was checking if `job["status"] == "pending"` but then did `await asyncio.sleep(0.01)` *before* transitioning the status to `"processing"`. Because of this await yielding execution control to the event loop, multiple concurrent worker coroutines saw the same job as `"pending"` and dequeued/processed it concurrently.
2. In `worker.py`, caught exceptions in the processing loop were logged but `queue.fail()` was never called to report the failure. This left failed jobs permanently in the `"processing"` status (making them appear stuck/disappeared) and prevented retries.
**Source:** `job_queue.py:22-28`, `worker.py:17-21`

## Backlinks
- [2026-07-31](../activity-log/2026/2026-07/2026-07-31.md) — Fixed concurrency and exception handling defects in the background job processor.
