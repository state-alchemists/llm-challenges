# Technical Note: Asyncio Checkout Concurrency

Handling race conditions in concurrent Python `asyncio` code requires careful management of critical sections.

## Key Learnings
- **Non-atomic Check-then-Act**: Checking stock and then later decrementing after an async action (like a payment charge `await`) creates a massive race condition. Multiple concurrent tasks will see sufficient stock and proceed to charge, leading to overselling or ghost charges.
- **Lock Lifetime and Event Loop Binding**: Instantiating a synchronisation primitive like `asyncio.Lock()` at import/module level is extremely dangerous when running multiple event loops sequentially (e.g. in test suites using `asyncio.run()`). The lock will be bound to the first loop, causing subsequent runs in new loops to crash with `RuntimeError: Task got Future attached to a different loop`.
- **Instance-bound Lock**: Binding the `asyncio.Lock` instance to the life of the dynamic `Inventory` object (instantiated inside the running loop) resolves loop mismatch errors perfectly and keeps trials isolated.

## Backlinks
- [Root](../index.md)
- [Technical Index](index.md)
- [Checkout Integration Bug Project](../projects/checkout-integration-bug.md)
- [2026-06-19 Log](../activity-log/2026/2026-06/2026-06-19.md)
