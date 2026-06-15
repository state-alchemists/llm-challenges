---
slug: checkout-toctou-fix
---
# Checkout TOCTOU Race — Fix

**Context:** `checkout()` in the e-commerce checkout flow runs concurrently via `asyncio.gather`.
**Root cause:** Time-of-check-to-time-of-use race. `check_stock(quantity)` and `decrement(quantity)` are separate coroutine calls with a payment call in between. Concurrent checkout coroutines all see the same initial stock value during `check_stock`, then proceed to payment, and finally race on `decrement`. The ones that lose the race have already been charged — producing ghost charges. With aggressive concurrency, the `decrement` guard condition can also fail to prevent overselling when more concurrent reservations pass the check than available stock.

**Fix:** Reorder the checkout flow:
1. `decrement(quantity)` first — atomically reserves stock (check-and-decrement is synchronous within the method, no yield point between the guard and the subtraction).
2. `gateway.charge()` second — only attempted if stock was confirmed reserved.
3. On payment failure, `inventory.increment(quantity)` releases the reservation.

**Why this works:** `Inventory.decrement()` does `await asyncio.sleep()` then a synchronous `if self._stock >= quantity: self._stock -= quantity` — no `await` between check and mutation, so single-threaded Python guarantees atomicity. The only window for a race is during the sleep, which is fine because that's just a delay before running the atomic check-and-subtract.

**Files changed:** `checkout.py` — restructured the three-step flow.
**No changes to public interfaces** of `Inventory` or `PaymentGateway`.

**Source:** `checkout.py:13-30`

## Backlinks
