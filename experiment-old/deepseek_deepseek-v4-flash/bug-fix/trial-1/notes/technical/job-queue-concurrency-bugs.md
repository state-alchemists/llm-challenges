---
slug: job-queue-concurrency-bugs
---
# Job Queue Concurrency Bugs

**Context:** The `JobQueue` + `Worker` async job processing system in the bug-fix challenge.
**Finding:** Two independent bugs — a race condition in dequeue causing duplicate processing, and a missing fail call causing vanishing failures.

## Bug 1: Race condition in `dequeue()`

**Root cause:** `job_queue.py:22` — `dequeue()` checked `job["status"] == "pending"`, then `await asyncio.sleep(0.01)`, then set `job["status"] = "processing"`. The `await` yielded control to other workers, all of whom also saw the job as "pending" and claimed it.

**Fix:** Move `job["status"] = "processing"` before the `await`. Race window eliminated.

**Source:** `job_queue.py:22`

## Bug 2: `queue.fail()` never called on exception

**Root cause:** `worker.py:14` — the `except` block only printed the error. The job stayed in "processing" status permanently, invisible to retry logic and excluded from the "failed" count.

**Fix:** Added `queue.fail(job["id"], str(e))` after the print. The job now properly transitions through retry cycles and lands in "failed" status when retries are exhausted.

**Source:** `worker.py:14`

## Backlinks
- [2026-05-30 activity](activity-log/2026/2026-05/2026-05-30.md) — Diagnosed and fixed both bugs
