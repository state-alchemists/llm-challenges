---
slug: ecommerce-checkout-project
---
# E-Commerce Checkout — concurrent bug fix

**Context:** An e-commerce checkout service hit production incidents: overselling (negative inventory) and ghost charges (charged but no item delivered).
**Symptom:** 12 concurrent orders against stock=5 with 25% payment failure rate. Ghost charges reproduced in 20/20 runs; overselling race exists but tighter timing window.
**Root cause:** TOCTOU race between `check_stock`/`decrement` + charge-before-reserve ordering.
**Fix:** `Inventory.reserve()` (atomic check-and-decrement via `asyncio.Lock`) + reserve-then-charge with payment-failure compensation.
**Verification:** 50/50 clean runs — no errors, no ghost charges, no negative stock, total charged always matches successful orders × price.
**Source files:** `inventory.py`, `checkout.py`, `payments.py` (unchanged), `main.py` (unchanged)

## Backlinks
- [checkout-race-condition technical note](../technical/checkout-race-condition.md) — root cause detail
- [2026-07-29 activity log](../activity-log/2026/2026-07/2026-07-29.md) — fix implemented here
