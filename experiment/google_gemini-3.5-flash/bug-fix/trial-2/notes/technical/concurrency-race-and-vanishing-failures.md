---
slug: concurrency-race-and-vanishing-failures
---
# Concurrency Race & Vanishing Failures in Job Queue

**Context:** Applies to multi-worker cooperative multitasking systems using asyncio.
**Finding:** 
1. Checking for a state and yielding control (`await`) before updating that state creates a race condition where multiple workers can select and process the same item simultaneously.
2. If exceptions inside workers are caught but not reported back to the queue (e.g. by invoking `fail()`), those failed jobs will never retry or update their status to "failed", remaining indefinitely in the "processing" state.
**Source:** `job_queue.py:23-28`, `worker.py:15-18`
