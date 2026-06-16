# Asyncio Reserve-Then-Charge Pattern

## Context

E-commerce checkout with concurrent coroutines sharing mutable state (inventory, payment gateway) via `asyncio.gather`.

## Problem

Two related race conditions in async check-then-act flows:

1. **TOCTOU (Time-of-check-time-of-use)**: `check_stock()` and `decrement()` are separate `async` calls with `await asyncio.sleep()` yield points. All concurrent coroutines pass `check_stock` before any calls `decrement`, so more items are "reserved" than exist.

2. **Charge-then-decrement ordering**: Successful charges with failed decrements produce ghost charges — customer pays but receives no item.

## Solution: Reserve-Then-Charge

1. **`reserve(quantity) -> bool`**: Atomic check-and-decrement under `asyncio.Lock`. No yield between check and mutation. Replaces the separate `check_stock` → `decrement` two-step.

2. **`release(quantity)`**: Atomic increment under lock — rollback when a downstream step (e.g. payment) fails.

3. **Checkout flow**: `reserve` → `charge` → `release` on charge failure. Every successful charge is guaranteed a reserved item; every failed charge releases the reservation.

4. **Idempotent `charge`**: Track processed `order_id`s in a set under lock. Duplicate calls return `True` without double-charging.

## Key Insight

In `asyncio`, code between `await` points runs atomically, but two separate `async` calls are never atomic together. The fix is to collapse the check-and-mutate into a single lock-protected operation with no intervening `await`.

## Backlinks
- [2026-06-16 activity log](../activity-log/2026/2026-06/2026-06-16.md) — applied this pattern to integration-bug challenge