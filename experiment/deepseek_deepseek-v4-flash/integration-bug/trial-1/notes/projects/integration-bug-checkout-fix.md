---
slug: integration-bug-checkout-fix
---
# Checkout concurrency fix (integration-bug)

**Context:** integration-bug challenge — concurrent checkout against shared `Inventory`/`PaymentGateway`; validator runs 6 trials sharing one interpreter.
**Finding:** check-then-act race in `checkout.py`: `check_stock` and `decrement` were separate awaits, so all 12 concurrent orders passed the stock check, ~9 charged, only 5 decremented → ghost charges (charged, no item) and charge/success mismatch. Fix: reserve stock atomically under a per-instance `asyncio.Lock` (`Inventory.reserve`), charge only after a successful reservation, and `release` the reservation if payment fails. Public interfaces of `Inventory`/`PaymentGateway` unchanged; added methods only.
**Source:** workdir/checkout.py, workdir/inventory.py (trial-1); verified EXCELLENT (score 1.0) by challenges/integration-bug/validator.py, 0 failures over 600 stress runs

## Backlinks
- [index](../index.md) — root index
- [2026-07-31 activity log](../activity-log/2026/2026-07/2026-07-31.md) — trial verified EXCELLENT (score 1.0)
