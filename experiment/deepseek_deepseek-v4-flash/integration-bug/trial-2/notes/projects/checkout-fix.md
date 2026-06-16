# Checkout Flow — TOCTOU Race Fix

**Bug**: E-commerce checkout suffered two concurrent-access bugs:
1. **Ghost charges**: customers charged but no item delivered (stock exhausted between `check_stock` and `decrement`)
2. **Overselling**: inventory could go negative under high concurrency

**Root cause**: `checkout()` performed the flow as `check_stock → charge → decrement`. The gap between `check_stock` (TOCTOU window) let concurrent orders all pass the stock check, then some failed at `decrement` after already being charged.

**Fix**: Reversed the flow to `decrement → charge → [on failure: increment]`.
- Stock is reserved first via `inventory.decrement()`. The method has no `await` between its guard (`if self._stock >= quantity`) and its mutation (`self._stock -= quantity`), making the check-and-debit effectively atomic under asyncio.
- If payment fails, the reservation is released via `inventory.increment(quantity)`.
- No changes to `Inventory` or `PaymentGateway` public interfaces.

**Files changed**: `checkout.py` only (swap call order, add increment on payment failure)

**Verified**: 20/20 simulation runs with 12 concurrent orders and 25% payment-failure rate produce zero invariants violated (no negative stock, no charge/order mismatch, no duplicate charges).

## Backlinks
- [activity: 2026-06-16](../activity-log/2026/2026-06/2026-06-16.md)
- [projects index](index.md)
