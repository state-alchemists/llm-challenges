# E-Commerce Checkout Challenge

Experiment: `experiment/deepseek_deepseek-v4-flash/integration-bug/trial-2/`

## Bug: TOCTOU race in checkout flow

**Root cause**: `checkout.py` checked stock, charged payment, then decremented stock — three separate async calls. Concurrent orders all passed the stock check, all charged, then the extras hit "inventory error after payment" (ghost charges, charged $600 for 5 items delivered).

**Fix**: Reserve-then-charge pattern. Added `Inventory.reserve()` that atomically checks stock and decrements under an `asyncio.Lock`. Stock is held before payment; released on payment failure.

## Files

- `checkout.py` — checkout logic (fixed)
- `inventory.py` — stock management with `asyncio.Lock` (added `reserve()`)
- `payments.py` — mock payment gateway (25% failure rate, unchanged)
- `main.py` — concurrent simulation runner (unchanged)

## Backlinks
- [2026-06-25 activity log](../activity-log/2026/2026-06/2026-06-25.md) — fix applied here
