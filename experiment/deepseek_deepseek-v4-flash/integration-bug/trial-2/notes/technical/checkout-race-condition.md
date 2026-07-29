---
slug: checkout-race-condition
---
# Reserve-then-charge: fix for concurrent checkout race conditions

**Context:** When multiple checkout coroutines run concurrently against shared inventory+payment state without synchronization.
**Finding:** Two bugs arose from non-atomic check-and-decrement and charge-before-reserve ordering:

1. **Overselling (negative stock):** `check_stock()` and `decrement()` were separate async calls with no lock. Between check and decrement, another coroutine could decrement first. Even within `decrement()`, the `if self._stock >= quantity` check and `self._stock -= quantity` write are separate Python bytecodes — two coroutines can both pass the check, then both read the same `self._stock` value and write the same (too-low) result.

2. **Ghost charges:** Checkout charged *before* decrementing. If payment succeeded but inventory was exhausted by the time `decrement()` ran, the customer was charged with no item delivered — and no refund mechanism existed.

**Fix:** Three-part minimal change:
- Added `asyncio.Lock` to `Inventory`, protecting all stock mutations (`check_stock`, `decrement`, `increment`, and the new `reserve`).
- Added `Inventory.reserve(quantity)` — atomic check-and-decrement in one locked operation.
- Reversed the checkout order to **reserve → charge → (compensate on failure)**: reserve atomically, then charge. If payment fails, the reserved stock is released via `inventory.increment()`.

**Source:** `inventory.py:37` (`reserve`), `checkout.py:11` (`reserve` first), `checkout.py:22` (compensation on payment failure)

## Backlinks
- [ecommerce-checkout project note](../projects/ecommerce-checkout.md) — project context
- [2026-07-29 activity log](../activity-log/2026/2026-07/2026-07-29.md) — fix implemented here
