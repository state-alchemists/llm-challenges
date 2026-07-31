---
slug: python-asyncio-check-then-act
---
# asyncio check-then-act across an await is a race

**Context:** When multiple coroutines share a mutable collection and one coroutine "claims" an item by checking a flag then setting it.
**Finding:** In single-threaded asyncio, code between an `await` and the next statement is a preemption point — any other coroutine can run there. A check-then-set split by `await` (e.g. `if status == "pending": await sleep(); status = "processing"`) lets every waiter pass the check on the same item, so each claims it. Fix: perform the mutation synchronously before any `await` (or guard with a Lock), so the check-and-set is atomic with respect to the event loop.
**Source:** `job_queue.py:22-28` (fixed in bug-fix trial-1); root cause reproduced in `main.py` run

## Backlinks
- [index](../index.md) — root HUD; listed under Recent Insights
- [index](index.md) — technical index
- [bug-fix challenge](../projects/bug-fix-challenge.md) — this was the duplicate-processing root cause
- [2026-07-31 log](../activity-log/2026/2026-07/2026-07-31.md) — fixed here
