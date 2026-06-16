---
slug: asyncio-checkout-concurrency
---
# Asyncio Checkout Concurrency

**Context:** When designing async checkouts with potential race conditions across stock-checking, payment, and decrementing.
**Finding:** Concurrent coroutines can check stock and find it available, then concurrently proceed to charge and decrement, leading to overselling or ghost charges. Creating an `asyncio.Lock` inside the `Inventory` instance and serializing the entire checkout process with `async with inventory.lock:` guarantees correctness.
**Source:** checkout.py:12

## Backlinks
- [2026-06-15 activity log](../activity-log/2026/2026-06/2026-06-15.md) — implemented fix for integration bug
- [root index](../index.md) — featured recent insight
- [technical index](index.md) — listed technical note
