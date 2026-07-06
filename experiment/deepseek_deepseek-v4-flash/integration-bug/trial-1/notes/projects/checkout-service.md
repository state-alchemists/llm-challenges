---
slug: checkout-service-toctou-fix
---
# Checkout Service — TOCTOU Race Fix

**Context:** A concurrent e-commerce checkout system with 12 concurrent orders competing for 5 items of stock.
**Finding:** The checkout flow had a classic TOCTOU (time-of-check-time-of-use) race condition between `check_stock()` and `decrement()` — all coroutines passed the stock check before any had decremented, causing overselling and ghost charges.

**Source:** checkout.py, inventory.py — analysed and fixed in this trial

## Root Cause

In the original `checkout.py`, the flow was:

1. `check_stock(quantity)` — reads `self._stock` and returns True/False
2. If available → `gateway.charge()` — records payment
3. `decrement(quantity)` — reads `self._stock` again and decrements

Because steps 1 and 3 are separate `async` calls with `await` gaps, all 12 concurrent coroutines passed `check_stock()` (seeing stock=5 ≥ 1) before any executed `decrement()`. Coroutines 6-12 then hit `decrement()` after stock was already drained — but by then the payment had already been recorded. Result: customers charged (total $900) but only 5 items delivered (expected $500). Stock never went negative only because `decrement()` had its own guard.

## Fix

**Pattern:** Reserve-then-charge with atomic reservation and rollback on payment failure.

### `inventory.py` — Added `try_reserve()` and asyncio.Lock

- Added `asyncio.Lock` to serialise stock mutations
- `try_reserve(quantity)` — atomically checks and decrements stock under the lock
- `decrement()` and `increment()` also protected by the same lock
- `check_stock()` intentionally left lock-free (read-only, eventual consistency is acceptable for pre-checks)
- Public interface unchanged; new method added

### `checkout.py` — New flow

1. `try_reserve(quantity)` — atomically reserves stock (check + decrement)
2. If reserved → `gateway.charge()` — records payment
3. If payment fails → `increment(quantity)` — releases reservation

Every successful charge now corresponds to exactly one reserved-and-delivered item. Payment failures release the held stock for other orders.

## Verification

5 runs of `main.py` with 12 orders × 5 stock × 25% payment failure rate:

- **Inventory never negative**: remaining stock in {0, 1, 2} — always ≥ 0
- **Charges match deliveries**: total charged = successful orders × $100 in every run
- **No ghost charges**: all "payment failed" orders return stock via `increment()`
- **No duplicate charges**: all runs report 0 duplicates

## Backlinks
- [../index.md](../index.md) — HUD entry for recent insights
- [index.md](index.md) — project index listing
- [activity-log/2026/2026-07/2026-07-06](../activity-log/2026/2026-07/2026-07-06.md) — fix implemented and verified here
