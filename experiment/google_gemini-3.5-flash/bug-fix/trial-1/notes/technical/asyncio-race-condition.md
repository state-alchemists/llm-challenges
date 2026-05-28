---
slug: asyncio-race-condition
---
# Concurrency and Exception Handling in Asyncio Job Queues

**Context:** Applies when implementing/debugging background task queues or workers in Python `asyncio`.
**Finding:** 
1. Avoid `await` statements (e.g., `asyncio.sleep`) inside critical sections *before* updating state flags (e.g., transition from `"pending"` to `"processing"`). Because `asyncio` is single-threaded and uses cooperative multitasking, operations between `await` statements are atomic. Modifying state flags *prior* to yielding control (via `await`) guarantees that other concurrent tasks see the updated state, preventing race conditions like duplicate dequeuing.
2. Ensure that any exception raised during job execution is caught and explicitly reported to the queue via a failure transition (e.g., `queue.fail()`), so that jobs are not left in an indefinite `"processing"` state and can be successfully retried or marked as failed.
**Source:** `job_queue.py:19-27`, `worker.py:15-18`
