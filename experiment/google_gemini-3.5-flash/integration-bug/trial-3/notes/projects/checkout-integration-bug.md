---
slug: checkout-integration-bug
---
# Checkout Integration Bug

**Context:** Diagnosing and fixing the checkout concurrency issues causing overselling and ghost charges.
**Finding:** Concurrent checkout requests checked stock and proceeded to charge before decrementing stock. This caused:
1. "Overselling" (negative inventory or item sold when out of stock) due to racing on checking stock.
2. "Ghost charges" (payment charged but no stock decremented) because payment was processed prior to stock decrement check in non-atomic steps.
Adding an `asyncio.Lock` serialization block in `checkout.py` surrounding stock verification, payment charging, and stock decrement ensures correctness and guarantees 100% atomic safety.

**Source:** checkout.py

## Backlinks
- [Index](../index.md)
- [activity-log/2026/2026-06/2026-06-23](../activity-log/2026/2026-06/2026-06-23.md) — bug diagnosed and fixed
