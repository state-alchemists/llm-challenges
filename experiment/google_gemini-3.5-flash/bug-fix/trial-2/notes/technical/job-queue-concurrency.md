# Job Queue Concurrency

## Concurrency Race Conditions
In a Python `asyncio` environment, cooperatively-scheduled tasks run on a single thread. However, control is yielded back to the event loop at any `await` point. If a state check and state mutation are separated by an `await` point (e.g. `await asyncio.sleep(...)`), another coroutine can enter and claim the same job, leading to duplicate processing.

### Remediation
1. **Mutex/Locks**: Utilize `asyncio.Lock()` to serialize access to critical code sections (like `dequeue`).
2. **Reordering**: Move state mutations synchronously preceding any `await` yield points so checking and setting the state happens atomically within the same cooperative scheduling window.

## Vanishing Failures
When workers catch general exceptions (`except Exception`) but do not notify the task orchestrator or queue about the crash, the queue status for that job remains "processing" indefinitely. This results in jobs getting "stuck" and disappearing from the list of retriable tasks.

### Remediation
Always invoke queue notification endpoints (e.g., `queue.fail(job_id, error_msg)`) in the exception block to transition the job back to `pending` (for retries) or to `failed`.

## Backlinks
- [index.md](../index.md)
