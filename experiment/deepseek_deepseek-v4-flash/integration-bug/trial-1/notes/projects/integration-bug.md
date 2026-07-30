# integration-bug — Checkout Concurrency Fix

## Bugs Diagnosed

### 1. Ghost charges (charge success, no item delivered)
`checkout.py` charged the payment gateway **before** decrementing inventory. Due to a TOCTOU race, `decrement()` could return `False` after a successful charge — customer paid for nothing.

### 2. Overselling (inventory race condition)
`check_stock()` and `decrement()` were separate coroutines with `await` gaps. Concurrent orders all passed the stock check before any could decrement, allowing up to 12 charges for 5 items.

## Fix

**Pattern**: Reserve → Charge. Stock is decremented atomically (under `asyncio.Lock`) before payment is attempted. On payment failure, the reservation is released via `inventory.increment()`. No code path exists where charge succeeds but item is not reserved.

### Files changed

| File | Change |
|------|--------|
| `inventory.py` | Added `asyncio.Lock` and `reserve(quantity)` — atomic check + decrement |
| `checkout.py` | Replaced `check_stock`+`charge`+`decrement` with `reserve`→`charge`+release |
| `payments.py` | Added `refund(order_id, amount)` for defensive completeness |

## Backlinks
- [root index](../index.md)
- [projects index](index.md)
- [2026-07-30 activity](../activity-log/2026/2026-07/2026-07-30.md) — fix implemented and verified
