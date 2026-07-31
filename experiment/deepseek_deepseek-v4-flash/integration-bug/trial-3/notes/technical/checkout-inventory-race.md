---
slug: checkout-inventory-race
---
# Checkout: check-then-act race and ghost charges

**Context:** `integration-bug` challenge — concurrent checkout against `Inventory` (asyncio) with mock `PaymentGateway` (25% failure).
**Finding:** Root cause was the check-then-act sequence in `checkout()`: `check_stock()` → `gateway.charge()` → `decrement()` are three separate awaits, so N concurrent orders all pass the stock check, all get charged, but only `stock`-many decrements succeed. The decrement losers are charged with no item and no refund → ghost charges (`total_charged > successful * price`). The overselling side is the same race.
**Fix:** Atomic reservation. Added per-instance `asyncio.Lock` to `Inventory` plus `reserve(quantity)` (check+decrement under lock, returns bool) and `release(quantity)` (compensation). `checkout()` now: `reserve` → `charge` → on failure/exception `release` → SUCCESS. Charge happens exactly once, only after stock is guaranteed. Public interfaces of `Inventory`/`PaymentGateway` unchanged.
**Source:** `experiment/deepseek_deepseek-v4-flash/integration-bug/trial-3/workdir/checkout.py:13-30`, `inventory.py:26-38`, `challenges/integration-bug/validator.py` (invariants: `stock == INITIAL - successful`, `charged == successful * price`, no duplicate charges; AST requires a Lock/Semaphore instantiation).

## Backlinks
- [index](../index.md) — journal HUD
