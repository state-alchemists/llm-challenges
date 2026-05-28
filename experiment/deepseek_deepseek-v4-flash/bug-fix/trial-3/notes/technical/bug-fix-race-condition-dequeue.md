---
slug: bug-fix-race-condition-dequeue
---
# Bug: Race condition in JobQueue.dequeue — duplicate processing

**Context:** Multi-worker async job processor where `dequeue()` checks `status == "pending"` then `await` before setting `status = "processing"`.
**Finding:** The `await asyncio.sleep(0.01)` between the status check and the status assignment creates a race window. All concurrent workers pass the check before any sets the status, so every worker dequeues the same job (5x processing for 5 workers).
**Fix:** Wrap the check-and-set in `asyncio.Lock` so the operation is atomic. Also an alternative is reordering so the status assignment happens before the await.
**Source:** `job_queue.py:dequeue`
