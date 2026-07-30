---
slug: ecommerce-checkout-lock
---
# E-Commerce Checkout concurrency issues solved with decrement-first pattern

**Context:** High concurrency checkout transactions causing overselling and ghost charges.
**Finding:**
1. Overselling is caused by concurrent `check_stock` reading stale stock levels before concurrent checkouts decrement them.
2. Ghost charges are caused by charging a customer successfully and then failing to decrement/allocate stock, with no refund.
3. Solved by synchronizing all inventory transactions (`decrement`, `increment`, `check_stock`) using an `asyncio.Lock()` in `inventory.py`.
4. In `checkout.py`, implemented a "decrement-first" reservation pattern with increment-compensation on failure. This keeps payment network calls (which take 0.03s) outside the inventory lock, maximizing concurrency.

**Source:** checkout.py, inventory.py

## Backlinks
- [HUD](../index.md)
- [Projects Index](index.md)
- [2026-07-30 log](../activity-log/2026/2026-07/2026-07-30.md) — Solved checkout issues
