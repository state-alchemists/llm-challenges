# Asyncio Cooperative Concurrency

In Python's `asyncio` framework, task execution is single-threaded and cooperative. Task context switches only occur at explicit yield points (i.e., `await` expressions).

## Key Learning: Atomic State Transitions

If a state transition (check-and-set operation) does not perform any `await` calls between checking the state and writing the new state, the transition is completely atomic with respect to other asyncio tasks.

### Anti-pattern
Awaiting an operation (like simulating latency via `await asyncio.sleep(0.01)`) *after* checking state but *before* writing the state leads to race conditions under concurrent workloads:
```python
if job["status"] == "pending":
    await asyncio.sleep(0.01) # Yields control: other tasks find the same "pending" job!
    job["status"] = "processing"
```

### Correct Pattern
Perform state mutation immediately after checking, prior to any `await` calls:
```python
if job["status"] == "pending":
    job["status"] = "processing" # Atomic write
    await asyncio.sleep(0.01) # Safe to yield control now
```

## Backlinks
- [Technical Index](index.md)
- [Journal Index](../index.md)
- [2026-07-30 Activity Log](../activity-log/2026/2026-07/2026-07-30.md)
