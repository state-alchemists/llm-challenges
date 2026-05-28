---
slug: vanishing-failures
---
# Worker: exceptions swallowed without failing the job

**Context:** `worker.py:process_job()` — the `except` block on job processing errors.
**Finding:** When `job["payload"].get("raise_error")` raises `RuntimeError`, the `except Exception` handler only printed the error and let the `while True` loop continue. It never called `queue.fail()`, so the job remained in "processing" status forever — invisible to retry logic and never counted as failed.
**Fix:** Added `queue.fail(job["id"], str(e))` to the except block. The queue's `fail()` method handles retries (re-queues as "pending" if retries < max_retries, marks "failed" otherwise).
**Source:** `worker.py:18`
