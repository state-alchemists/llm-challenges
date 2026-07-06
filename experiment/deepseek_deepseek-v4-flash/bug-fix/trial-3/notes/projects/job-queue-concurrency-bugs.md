---
slug: job-queue-concurrency-bugs
---
# Job Queue: TOCTOU race and missing fail call

**Context:** The `job_queue.py` / `worker.py` system processes background jobs with concurrent workers via `asyncio.gather`. Two bugs caused duplicate processing and lost failures.

**Finding:** Two independent defects:

1. **TOCTOU race in `dequeue()`** (`job_queue.py:dequeue`): The `await asyncio.sleep(0.01)` sat between the `"pending"` status check and the `"processing"` status write. Multiple worker coroutines would all see the job as `"pending"` during the sleep window, all claim it, and all process it — each job ran 5 times with 5 workers. Fix: set `job["status"] = "processing"` before the sleep, making the check-and-claim atomic.

2. **Missing `fail()` call in worker exception handler** (`worker.py:process_job`): The `except` block printed the error but never called `queue.fail()`. Jobs that crashed stayed in `"processing"` status indefinitely — they were invisible to retry logic and never surfaced as `"failed"`. Fix: added `queue.fail(job["id"], str(e))` in the except block, which triggers the retry-or-fail logic in `JobQueue.fail()`.

**Source:** job_queue.py:21-26, worker.py:14-17

## Backlinks
- [root index](../index.md)
- [project index](index.md)
- [2026-07-06 activity](../activity-log/2026/2026-07/2026-07-06.md) — bugs diagnosed and fixed
