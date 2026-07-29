---
slug: checkout-integration-bug
---
# Checkout Service Integration Bug Fix

**Context:** Production incidents regarding Overselling (negative stock) and Ghost Charges.
**Finding:** Checkout service checked stock, charged payments, and decremented inventory in that order without atomic concurrency protection. Under concurrency, multiple checkouts passed stock checks, charged customers, but failed to secure inventory. The solution is:
1. Try to decrement (reserve) the stock first using an atomic decrement operation.
2. If decrement fails, return "out of stock" immediately.
3. If decrement succeeds, try to charge the payment gateway.
4. If payment fails (or an exception is raised), increment the stock back (rollback).
5. Add `asyncio.Lock()` to `Inventory` methods (`check_stock`, `decrement`, `increment`) to ensure absolute thread-safety / coroutine-safety.
**Source:** checkout.py, inventory.py

## Backlinks
- [HUD](../index.md) — referenced as major project
- [Projects Index](index.md) — project listing
- [2026-07-29 Activity Log](../activity-log/2026/2026-07/2026-07-29.md) — project bug fixed
