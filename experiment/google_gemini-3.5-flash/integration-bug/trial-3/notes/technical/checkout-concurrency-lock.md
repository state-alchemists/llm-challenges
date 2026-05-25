---
slug: checkout-concurrency-lock
---
# E-commerce Checkout Concurrency Synchronization using Async Lock

**Context:** Applies when concurrent async checkout requests can cause race conditions (such as double/ghost charging and overselling) due to yield points in-between check-stock and charge/decrement operations.
**Finding:** Synchronizing the critical section (checking stock, processing payment, and decrementing inventory) using an `asyncio.Lock` ensures that checkout is processed atomically. Storing the lock lazily on the `Inventory` instance avoids global locks and preserves clean public interfaces.
**Source:** checkout.py:10, inventory.py:10
