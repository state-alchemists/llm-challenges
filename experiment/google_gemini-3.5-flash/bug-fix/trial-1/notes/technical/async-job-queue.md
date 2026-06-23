---
slug: async-job-queue
---
# Concurrency & Failure Handling in Async Job Queue

**Context:** When implementing an asynchronous concurrent job queue.
**Finding:** Workers must transition job status to `"processing"` *before* yielding control (such as awaiting IO or delay) inside `dequeue` to prevent race conditions leading to duplicate processing. Additionally, exceptions during processing must be caught and explicitly reported to the queue using `fail(job_id, error)` to prevent stuck/vanishing jobs.
**Source:** `job_queue.py:24`, `worker.py:16`

## Backlinks
- [HUD](../index.md) — linked as a recent insight
- [activity-log/2026/2026-06/2026-06-23](../activity-log/2026/2026-06/2026-06-23.md) — analyzed and resolved duplicate processing and vanishing failures
- [Technical Index](index.md)
