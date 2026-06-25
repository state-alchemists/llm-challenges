# Integration Bug Trial 3 — E-Commerce Checkout

**Repo:** `experiment/deepseek_deepseek-v4-flash/integration-bug/trial-3/workdir`

**Bug:** Concurrent checkout overselling + ghost charges

**Fix:** Reserve-then-charge pattern with `asyncio.Lock` in Inventory

**Files:**
- `checkout.py` — checkout logic (fixed)
- `inventory.py` — stock management (added `try_reserve`, `release_reservation`)
- `payments.py` — mock payment gateway (unchanged)
- `main.py` — concurrent simulation runner (unchanged)

## Technical details

- [concurrent-inventory-checkout pattern](../technical/concurrent-inventory-checkout.md)
- [2026-06-25 fix entry](../activity-log/2026/2026-06/2026-06-25.md)

## Backlinks

- [index](../index.md) — journal root
- [projects index](index.md) — directory index
- [2026-06-25 activity log](../activity-log/2026/2026-06/2026-06-25.md) — fix implemented and verified
- [concurrent-inventory-checkout](../technical/concurrent-inventory-checkout.md) — technical pattern used
