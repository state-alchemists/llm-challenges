---
slug: job-queue-atomic-claim-and-failure-reporting
---
# Job queue: claim must be atomic, failures must call fail()

**Context:** Single-threaded asyncio job queue where multiple worker coroutines dequeue from one shared dict of jobs.
**Finding:** The bug-fix challenge (job_queue.py / worker.py) had two root causes. (1) Duplicate processing: `dequeue()` awaited `asyncio.sleep(0.01)` between the `status == "pending"` check and the `status = "processing"` assignment, so every worker saw the same job as pending and processed it — reproduced as every job being picked up by all 5 workers. Fix: assign the status before any await so there is no suspension point between check and set (atomic claim in asyncio). (2) Vanishing failures: `worker.py`'s `except` block only printed the error and never called `queue.fail(...)`, so crashed jobs stayed `processing` forever — never retried, never marked `failed`. Fix: call `queue.fail(job["id"], str(e))`; the queue then retries until `max_retries` and marks `failed`.
**Source:** workdir/job_queue.py:30-36, workdir/worker.py:17-19 (experiment/deepseek_deepseek-v4-flash/bug-fix/trial-3)

## Backlinks
- [journal index](../index.md) — HUD entry for this insight
- [technical index](index.md) — directory index for this note
- [2026-07-31 log](../activity-log/2026/2026-07/2026-07-31.md) — bug fixed this session
