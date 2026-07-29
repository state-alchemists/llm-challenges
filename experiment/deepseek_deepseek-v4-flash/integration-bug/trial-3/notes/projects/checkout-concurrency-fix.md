# Checkout Concurrency Fix

## Problem

The e-commerce checkout service had two production bugs under concurrent load:

1. **Overselling**: `check_stock()` (read) and `decrement()` (write) were separate coroutine calls with no atomicity. Multiple orders could all see stock >= 1, pass payment, then all subtract — driving inventory negative.

2. **Ghost charges**: Payment succeeded before stock was decremented. When decrement failed (stock already taken by another order), the customer was charged with no item delivered and no successful order recorded.

## Root Cause

Three distinct races:

| Race | Mechanism | Effect |
|------|-----------|--------|
| TOCTOU between `check_stock` and `decrement` | `check_stock` returns True, then another coroutine decrements before this one gets to `decrement` | Overselling |
| TOCTOU inside `decrement` | `if self._stock >= qty` check and `self._stock -= qty` are separate async operations without a lock | Inventory goes negative |
| Charge-then-decrement ordering | Payment committed before stock is secured | Ghost charges |

## Fix

**Pattern**: Reserve-before-charge with rollback on payment failure.

### Changes

**`inventory.py`** — Added atomic `reserve()` and `release()` methods under an `asyncio.Lock`:

- `reserve(quantity)` — atomically checks stock and decrements in one critical section. Single source of truth for availability.
- `release(quantity)` — returns reserved stock (called when payment fails after a successful reserve).
- Existing `decrement()` and `increment()` also locked for safety, though `reserve()` is the new primary interface.

**`payments.py`** — Added `asyncio.Lock` around the `total_charged` / `charges` append to prevent concurrent write races (lost updates, interleaved appends).

**`checkout.py`** — New flow:

1. `inventory.reserve(quantity)` — atomic check-and-decrement
2. If reserve fails → "out of stock", return False
3. `gateway.charge(...)` — attempt payment
4. If charge fails → `inventory.release(quantity)` to restore stock, return False
5. If charge succeeds → SUCCESS, return True

### Invariants restored

- Inventory never goes below zero (`reserve` is an atomic compare-and-swap)
- Every successful charge corresponds to exactly one delivered item (stock reserved before charge; if charge succeeds, stock is already decremented)
- No order charged more than once (idempotent charge with lock-protected accounting)

### Verification

Run 10 times with 12 concurrent orders against stock=5, 25% payment failure rate. Zero errors across all runs: no negative stock, no charge/success mismatch, no duplicate charges.

## Files Changed

- `checkout.py` — replaced check_stock+decrement with reserve+release
- `inventory.py` — added `_lock`, `reserve()`, `release()`
- `payments.py` — added `_lock` to `charge()` critical section

## Backlinks
- [2026-07-29](../activity-log/2026/2026-07/2026-07-29.md) — fix implemented and verified
