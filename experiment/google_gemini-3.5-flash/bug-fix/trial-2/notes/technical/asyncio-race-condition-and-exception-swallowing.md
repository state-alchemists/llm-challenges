---
slug: asyncio-race-condition-and-exception-swallowing
---
# Asyncio Race Condition and Exception Swallowing

**Context:** Applies when implementing asynchronous background job processors with concurrent workers and error handling.
**Finding:** Updating job status in an asynchronous generator/iterator *after* an `await` yield point causes multiple concurrent workers to see the job as "pending" and process it concurrently, causing duplicate processing. Furthermore, swallowing exceptions in workers without propagating or calling failure hooks leads to "stuck/vanishing" jobs.
**Source:** job_queue.py:22, worker.py:16
