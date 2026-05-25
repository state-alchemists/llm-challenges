---
slug: bug-fix-duplicate-processing-and-vanishing-failures
---
# Bug Fix: Duplicate Processing & Vanishing Failures in Async Job Queue

**Context:** Production bug-fix challenge at `job_queue.py` and `worker.py`.
**Finding:** Two independent bugs — a TOCTOU race condition in `dequeue()` and a missing `queue.fail()` call in the worker's exception handler.

## Bug 1: Duplicate Processing (Race Condition)

**Root cause:** `job_queue.py:27` — `dequeue()` checks `job["status"] == "pending"` and then awaits `asyncio.sleep(0.01)` before setting `job["status"] = "processing"`. The `await` yields the event loop, so all 5 concurrent workers see the same job as "pending", pass the check, and all process it.

**Fix:** Removed `await asyncio.sleep(0.01)` between the check and the assignment. In Python asyncio (single-threaded), consecutive synchronous statements run atomically w.r.t. other coroutines — no yield point, no race.

**Source:** `job_queue.py:25-30`

## Bug 2: Vanishing Failures

**Root cause:** `worker.py:17` — the `except Exception as e` block prints the error but never calls `queue.fail()`. The job stays `"processing"` forever — never transitions to `"failed"`, never goes back to `"pending"` for retry. The job "disappears" from a retry/failure tracking perspective.

**Fix:** Added `queue.fail(job["id"], str(e))` in the except block. Jobs now properly cycle through retries and land in `"failed"` when retries are exhausted.

**Source:** `worker.py:16-18`

## Verification

Before fix: `Done: 10, Failed: 0, Stuck: 2`. Every job processed 5× (all workers), failed jobs stuck in `"processing"`.
After fix: `Done: 10, Failed: 2, Stuck: 0`. Each job processed once by a single worker. Bad tasks retried `max_retries` times then terminate as `"failed"`.
