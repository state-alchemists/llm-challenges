---
slug: concurrency-and-error-propagation
---
# Concurrency and Error Propagation in Async Job Queues

**Context:** Applies to asynchronous background job queues where multiple concurrent workers retrieve and process tasks from a single queue.
**Finding:**
1. **Duplicate Processing:** If `dequeue` yields control using `await` (e.g., simulating latency/async operations) before updating job status, multiple concurrent workers can interleave, see the same job as `"pending"`, and process it. Serializing the dequeue logic using an `asyncio.Lock` prevents this race condition.
2. **Vanishing Failures:** Worker exception blocks that log/print errors but do not notify the queue controller (e.g., calling `queue.fail()`) cause crashed jobs to remain forever in an intermediate `"processing"` state, preventing retry logic from triggering.

**Source:** `job_queue.py:22-30`, `worker.py:16-22`
