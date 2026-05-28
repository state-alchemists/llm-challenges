---
slug: bug-fix-vanishing-failures
---
# Bug: Worker swallows exceptions — failures vanish from queue

**Context:** `worker.py:process_job` catches exceptions in the job handler but never calls `queue.fail()`.
**Finding:** The `except` block prints the error message but doesn't transition the job's status. The job stays `"processing"` forever, so it never retries and never shows as `"failed"`. Retries and failure tracking are dead code.
**Fix:** Add `queue.fail(job["id"], str(e))` in the except block so the job gets retried (up to max_retries) and eventually marked as `"failed"`.
**Source:** `worker.py:process_job`
