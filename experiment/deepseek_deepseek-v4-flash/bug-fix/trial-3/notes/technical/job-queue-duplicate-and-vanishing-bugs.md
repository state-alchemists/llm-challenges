---
slug: job-queue-duplicate-and-vanishing-bugs
---
# Job Queue: duplicate processing and vanishing failures

**Context:** Async job queue with `dequeue()` race condition and missing failure handling in `worker.py`.
**Finding:** Two independent bugs occurred in production:

1. **Duplicate processing** (`job_queue.py:20`): `dequeue()` had `await asyncio.sleep(0.01)` between checking `status == "pending"` and setting `status = "processing"`. This TOCTOU window let all concurrent workers claim the same job — every job was executed 5× in the simulation.

2. **Vanishing failures** (`worker.py:17-18`): The `except Exception` block in `process_job()` printed the error but never called `queue.fail()`. Crashed jobs remained in `"processing"` state — not retried, not counted as failed, effectively vanished from the queue.

**Fix:** Removed the `await` from `dequeue()` (atomic mark-and-return). Added `queue.fail(job["id"], str(e))` in the worker's except block.
**Source:** `job_queue.py:20-25` (dequeue), `worker.py:17-18` (except handler)
