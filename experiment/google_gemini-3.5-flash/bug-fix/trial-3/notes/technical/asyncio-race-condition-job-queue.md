---
slug: asyncio-race-condition-job-queue
---
# Asyncio Race Conditions and Job Processing Failures

**Context:** Applies when writing asynchronous (asyncio) background workers/job queues in Python.
**Finding:** Awaiting before marking a resource's status as reserved/processing yields control to the event loop, allowing other concurrent coroutines/workers to fetch the same resource and causing duplicate processing. State mutation must happen synchronously before any await. Additionally, exceptions during processing must be caught and reported to the queue (via `fail()`) to prevent tasks from remaining in the "processing" state indefinitely.
**Source:** job_queue.py:22, worker.py:18
