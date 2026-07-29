---
slug: background-job-processor
---
# Background Job Processor

**Context:** Diagnosing and fixing background job queue and processor issues.
**Finding:** Fixed two major issues in the job processing system:
1. **Duplicate Processing:** Fixed a concurrency bug in `JobQueue.dequeue` (in `job_queue.py`) where multiple asynchronous workers picked up the same job because control yielded via `await asyncio.sleep(0.01)` BEFORE the job status changed from `"pending"` to `"processing"`. Solved by changing status synchronously before the await.
2. **Vanishing Failures:** Fixed a bug in `worker.py` where exceptions raised during job execution were caught by workers but not reported back to the queue, causing them to stay in `"processing"` forever (stuck jobs). Solved by calling `queue.fail(job["id"], str(e))` in the exception handler.

**Source:** job_queue.py:24, worker.py:19

## Backlinks
- [index.md](../index.md) - HUD
- [projects index](index.md) - index of projects
- [2026-07-29 activity](../activity-log/2026/2026-07/2026-07-29.md) - logging the bug fixes
