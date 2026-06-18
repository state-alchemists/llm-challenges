# Job Processor

Persistent facts and notes on the background job processor.

## Architectural Notes
- The job processor consists of a queue (`job_queue.py`) and worker processor (`worker.py`).
- Cooperatively multitasked using Python's `asyncio`.

## Bug Fixes
- **Duplicate processing race condition**: Resolved in `JobQueue.dequeue` by changing status from `'pending'` to `'processing'` synchronously before any asynchronous yield (`await asyncio.sleep(...)`).
- **Vanishing failures / Stuck status**: Resolved by adding a call to `queue.fail(job["id"], str(e))` inside the worker exception block to notify the queue and trigger retry/failed logic.

## Backlinks
- [index](../index.md)
- [projects index](index.md)
- [2026-06-19 log](../activity-log/2026/2026-06/2026-06-19.md)
