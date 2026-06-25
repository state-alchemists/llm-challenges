---
slug: concurrency-bug-in-job-queue
---
# Concurrency Bug in Job Queue

**Context:** Fixed concurrent dequeue state transitions in asyncio queues and missing exception handlers in worker loops.
**Finding:** Synchronously transitioning status to `"processing"` in `dequeue` before any `await` ensures thread/coroutine-safety across workers. Additionally, unhandled exceptions in python worker tasks must propagate error/failure status to the queue using `fail`.
**Source:** job_queue.py:20-27, worker.py:16-19

## Backlinks
- [HUD Index](../index.md)
- [Technical Index](index.md)
- [2026-06-25 log](../activity-log/2026/2026-06/2026-06-25.md) — fix entry
