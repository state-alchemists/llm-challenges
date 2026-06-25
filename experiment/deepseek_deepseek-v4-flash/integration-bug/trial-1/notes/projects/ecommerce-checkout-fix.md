# E-Commerce Checkout Fix

**Root cause**: TOCTOU race condition in `checkout.py` — `check_stock()` and `decrement()` were separated by `gateway.charge()`, allowing concurrent orders to all pass the stock check before any decremented.

## Fix
1. **Reversed checkout order**: Reserve stock atomically (via `decrement()`) *before* charging. On payment failure, release stock via `increment()`.
2. **Payment idempotency**: `PaymentGateway.charge()` now checks for existing `order_id` before charging — prevents double-charge on retries.

## Files changed
- `checkout.py` — reordered operations, removed `check_stock()` call
- `payments.py` — added idempotency check in `charge()`

## Invariants guaranteed
- Stock never goes below zero
- Every charge corresponds to an item delivered
- No order charged more than once

## Verification
- Reproduced both bugs on original code
- 4 simulation runs post-fix: all invariants hold, including edge case of stock exhaustion with 0% payment failure rate

## Backlinks
- [2026-06-25 log](../activity-log/2026/2026-06/2026-06-25.md)
