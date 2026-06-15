# Bug-Fix: Job Queue Concurrency Defects

**Context:** LLM Challenges benchmark — a job queue (`job_queue.py`) and worker (`worker.py`) with two production-class concurrency bugs.

## Defect 1: TOCTOU Race in `dequeue()`

**Location:** `job_queue.py:dequeue()` — `job["status"] = "processing"` set *after* `await asyncio.sleep(0.01)`.

**Mechanism:** Two concurrent workers both check `job["status"] == "pending"` before either sets it to "processing". Both see "pending", both take the same job. Result: every job processed N times (once per worker).

**Fix:** Claim the job (`job["status"] = "processing"` ) before the await point.

## Defect 2: Missing `fail()` Call in Worker

**Location:** `worker.py:process_job()` — `except` block only printed the error.

**Mechanism:** A job that raises an exception is caught, printed, and silently abandoned. The status stays "processing", so it is never retried (retries only happen via `queue.fail()`) and never counted as "failed". The job vanishes from the system.

**Fix:** Call `queue.fail(job["id"], str(e))` in the except block.

## Verification

Simulation results after fix: `Done: 10`, `Failed: 2`, `Stuck: 0`.

## Backlinks
- [2026-06-15 activity log](../activity-log/2026/2026-06/2026-06-15.md) — fixes applied and verified
