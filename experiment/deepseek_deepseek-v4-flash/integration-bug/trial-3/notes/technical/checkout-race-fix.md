---
slug: checkout-race-fix
---
# Checkout Race Condition Fix

**Context:** Concurrent checkout flow with 12 orders competing for 5 stock units.
**Finding:** Three distinct bugs, all caused by the check-then-act pattern without synchronization:

1. **Ghost charges** (most visible: every run): `check_stock` passes → `charge` succeeds → `decrement` fails because stock was depleted by a concurrent order. Customer charged but receives nothing.

2. **Overselling**: The TOCTOU between `check_stock` and `decrement` allows multiple concurrent orders to both pass the stock check and succeed at charging, then race on `decrement`.

3. **Duplicate charges**: `charge` has no idempotency — retrying a failed checkout charges the same `order_id` again.

**Fix — three changes:**

- **`inventory.py`**: Added `asyncio.Lock`. Made `decrement` (and `increment`) atomic under the lock — the check-and-write race on `self._stock` is eliminated.
- **`payments.py`**: Added `asyncio.Lock`, `_charged_ids` set for idempotency (same `order_id` returns `True` without charging again), and `refund()` method to reverse a charge.
- **`checkout.py`**: After a successful charge, if `decrement` fails (no stock left), call `gateway.refund(order_id)` — no ghost charges.

**Source:** `inventory.py`, `payments.py`, `checkout.py`
**Verified:** 200 stress runs, zero errors.
