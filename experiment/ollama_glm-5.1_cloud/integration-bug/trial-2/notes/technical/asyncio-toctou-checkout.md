# asyncio TOCTOU Race in Checkout Flow

## Context

E-commerce checkout service with three modules: `checkout.py`, `inventory.py`, `payments.py`. The checkout flow processes concurrent orders via `asyncio.gather`.

## Bug

Original flow: `check_stock()` → `gateway.charge()` → `inventory.decrement()`.

This is a classic **time-of-check-to-time-of-use (TOCTOU)** race. When 12 orders run concurrently with only 5 items in stock:

1. **Overselling / ghost charges**: Multiple coroutines pass `check_stock()` before any `decrement()` runs. They all proceed to `gateway.charge()`. Some succeed at charging but then fail at `decrement()` — the customer is charged but receives no item, and there's no record of a successful order.

2. **Root cause**: Stock is checked separately from decrementing it, with an `await` (payment gateway) in between. No lock protects the check-then-modify sequence.

## Fix

Changed the order to **reserve-then-charge-then-rollback-on-failure**:

1. `inventory.decrement(quantity)` — atomically reserves stock under an `asyncio.Lock`
2. `gateway.charge()` — charges the customer
3. If charge fails: `inventory.increment(quantity)` — releases reserved stock

Added `asyncio.Lock` to `Inventory.__init__` and wrapped `decrement()` and `increment()` with `async with self._lock` to guarantee atomicity of the check-and-decrement within a single coroutine step.

## Key Insight

In `asyncio`, code between two `await` points runs atomically on the event loop. The bug was that `check_stock` and `decrement` were **separate** `async` calls with an `await` (the payment) between them. The fix makes reservation and charge a single atomic reserve-then-charge flow, with rollback on failure. The lock on `decrement`/`increment` provides defense-in-depth against future modifications that might add yield points inside the critical section.

## Backlinks
- [2026-06-23 activity log](../activity-log/2026/2026-06/2026-06-23.md) — bug diagnosed and fixed today