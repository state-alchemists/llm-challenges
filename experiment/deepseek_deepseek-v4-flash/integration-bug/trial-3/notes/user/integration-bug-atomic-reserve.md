---
slug: integration-bug-atomic-reserve
---
# Integration Bug: Atomic Reserve for Checkout

**Context:** The checkout flow in `checkout.py` had two race conditions in concurrent scenarios (12 orders racing for 5 items).
**Finding:** Two distinct bugs:
1. **Ghost charges** — TOCTOU between `check_stock` and `decrement`: orders passed stock check, got charged, then failed decrement because concurrent orders consumed the stock. Money taken, no item delivered.
2. **Overselling** — `decrement`'s internal check-and-modify (`if >=` / `-=`) is not atomic; concurrent decrements can both pass the guard and drive stock negative.

**Fix:** Added `asyncio.Lock` to `Inventory` and an atomic `reserve()` method that checks AND decrements under the lock. Restructured `checkout` to reserve-first-then-charge, rolling back with `increment()` on charge failure. This guarantees: stock never negative, no charge without a reserved item, each order charged at most once.

**Source:** `inventory.py:12-24`, `checkout.py:11-25`
