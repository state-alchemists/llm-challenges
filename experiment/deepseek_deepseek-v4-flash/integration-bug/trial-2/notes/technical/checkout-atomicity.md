---
slug: checkout-atomicity
---
# Checkout atomicity fix

**Context:** integration-bug challenge (checkout.py / inventory.py / payments.py); 12 concurrent orders over a 5-unit stock.
**Finding:** Root cause was a check-then-act split: `check_stock` (read) and `decrement` (write) were separate awaits, so all 12 orders passed the stock check, ~9 charged, only 5 decremented → charged-but-undelivered "ghost charges" ($900 charged vs $500 expected); the same split is a classic race that can push stock negative in a threaded/DB setting. Fix: add atomic `Inventory.reserve(quantity)` guarded by `asyncio.Lock` (check + decrement inside one critical section) and reorder checkout to reserve → charge → increment-on-payment-failure. Kept public interfaces of `Inventory`/`PaymentGateway`; only added `reserve`.
**Source:** challenges/integration-bug/validator.py (6 trials: stock == INITIAL_STOCK - successful, charged == successful*price, no duplicate order_ids) — result EXCELLENT 1.0; workdir/checkout.py, workdir/inventory.py

## Backlinks
- [Index](../index.md) — HUD
