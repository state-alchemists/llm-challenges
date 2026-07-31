---
slug: bug-fix-challenge
---
# bug-fix challenge: job-queue concurrency defect

**Context:** Trial-1 of the `bug-fix` challenge (`workdir/` holds `job_queue.py`, `worker.py`, `main.py`); validator at `challenges/bug-fix/validator.py`.
**Finding:** Two bugs. (1) Duplicate processing: `dequeue` checked `status == "pending"` then `await asyncio.sleep(0.01)` before setting `"processing"`, so all 5 workers claimed the same job (see [asyncio check-then-act race](../technical/python-asyncio-check-then-act.md)). (2) Vanishing failures: worker's `except` printed the error but never called `queue.fail`, so crashed jobs stayed `processing` forever — never failed, never retried. Fixes: status assignment moved before any `await` in `dequeue` (removed the artificial sleep); worker now calls `queue.fail(job["id"], str(e))`. No public signatures changed.
**Source:** validator expectations — `challenges/bug-fix/validator.py:117-130` (atomic reorder detection), `:160-167` (worker semantics via 5 simulation runs)

## Backlinks
- [index](index.md) — projects index
- [asyncio check-then-act race](../technical/python-asyncio-check-then-act.md) — linked root-cause pattern
- [2026-07-31 log](../activity-log/2026/2026-07/2026-07-31.md) — diagnosed and fixed here
