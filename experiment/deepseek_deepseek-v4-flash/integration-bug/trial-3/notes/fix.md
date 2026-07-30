# Checkout Fix: Atomic Reserve Pattern

## Root Cause

TOCTOU race in `checkout()` (`checkout.py:10-22`) between `check_stock` and `decrement`. 
The gap was wide enough (~40ms simulated latency) for multiple concurrent orders to pass
the stock check, get charged, then all fail at decrement except the first N (where N=stock).

**Ghost charges**: Payment taken, decrement fails, order returns `False` — customer charged
with no order record and no item.

## Changes

### `checkout.py`
Old flow: `check_stock` → `charge` → `decrement` (TOCTOU between check and decrement)
New flow: `reserve` (atomic check+decrement) → `charge` → `release` on payment fail
- `reserve` either allocates stock or fails — no window for another order to steal it
- If `charge` fails, `release` returns the stock to inventory

### `inventory.py`
Added `reserve(quantity)` — atomic check + decrement (single method, single coroutine)
Added `release(quantity)` — restore stock after a failed payment

### `payments.py`
Added `_charged_order_ids: Set[str]` — idempotency guard. Duplicate `charge()` call
for the same `order_id` returns `True` without recording a second transaction.

## Invariants Guaranteed

1. **Inventory never goes negative** — `reserve` checks before subtracting
2. **Every charge maps to one item** — stock is reserved before payment is attempted
3. **No order charged more than once** — idempotency set in PaymentGateway
