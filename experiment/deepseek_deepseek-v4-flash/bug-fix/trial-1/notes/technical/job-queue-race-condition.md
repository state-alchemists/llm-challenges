---
slug: job-queue-race-condition
---
# Job queue: TOCTOU race in dequeue

**Context:** `job_queue.py:dequeue()` — async workers claim pending jobs.
**Finding:** The `await asyncio.sleep(0.01)` between checking `job["status"] == "pending"` and setting `job["status"] = "processing"` creates a time-of-check-time-of-use race. In asyncio's cooperative multitasking, `await` yields control — so N concurrent workers all see the same job as "pending", all mark it "processing", and all return it. Every job gets processed N times instead of once.
**Fix:** Removed the `await asyncio.sleep(0.01)` — the check-and-set now happens without a suspension point, so only one worker can claim each job.
**Source:** `job_queue.py:18-21`
