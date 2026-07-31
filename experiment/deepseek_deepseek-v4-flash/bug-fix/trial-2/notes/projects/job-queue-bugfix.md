---
slug: job-queue-bugfix
---
# Job queue bugfix (trial-2)

**Context:** Background job processor simulation (job_queue.py + worker.py) in the bug-fix challenge workdir; 5 async workers process 12 jobs.
**Finding:** Two independent root causes. (1) `dequeue()` awaited `asyncio.sleep(0.01)` *between* checking `status == "pending"` and setting `status = "processing"` — the await yields the event loop, so every concurrent worker claims the same job and processes it (duplicate processing). Fix: assign the status before any await. (2) `worker.py`'s except block only printed the error; it never called `queue.fail()`, so crashed jobs stayed stuck in `"processing"` forever (vanishing failures, no retries). Fix: call `queue.fail(job["id"], str(e))` in the except block.
**Source:** workdir/job_queue.py:30-36; workdir/worker.py:19-21; validator at challenges/bug-fix/validator.py (race check = status assignment must precede any await in dequeue, or a Lock must be instantiated)

## Backlinks
- [activity-log 2026-07-31](../activity-log/2026/2026-07/2026-07-31.md) — fixed both root causes; validator EXCELLENT 1.0
