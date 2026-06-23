# Async Job Queue Project

## Overview
A simple in-memory asyncio background job queue simulation designed to evaluate model-driven coding agents.

## Concurrency and Exception Defects
1. **Duplicate Processing**:
   - In `JobQueue.dequeue()`, the check for pending jobs and setting of the state to `"processing"` was split by `await asyncio.sleep(0.01)`.
   - Under concurrency, multiple workers found the same job in `"pending"` status, slept concurrently, and then all returned the same job ID.
   - **Fix**: Synchronously mark the job `"processing"` *before* the `await` point so subsequent checks see the updated status.

2. **Vanishing Failures**:
   - In `worker.py`, when a job raised an exception, the worker caught it but never called `queue.fail(job_id, error)`.
   - This left the job in `"processing"` status forever (becoming "stuck"), and prevented any retries or final transition to `"failed"`.
   - **Fix**: Update the catch block in `worker.py` to call `queue.fail(job["id"], str(e))`.

## Backlinks
- [Projects Index](index.md)
- [2026-06-23 log](../activity-log/2026/2026-06/2026-06-23.md)
