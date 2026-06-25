# TOCTOU Race in Concurrent Checkout

When an async checkout flow separates stock-checking from stock-decrementing with a `charge()` call between them, concurrent orders all see the same available stock and all proceed to charge. The decrement at the end is too late — overselling and ghost charges result.

## Pattern: Reserve-Before-Charge

```
1. Reserve stock atomically (decrement)
2. Process payment
3. If payment fails, release stock (increment)
```

This ensures every successful charge has secured inventory first, and failed payments don't leak stock.

## Key insight

`decrement()` in `inventory.py` *already* does an atomic check-and-decrement within a single method call — the bug was purely in `checkout.py` sequencing the calls wrong.

## Backlinks
- [ecommerce-checkout-fix](../projects/ecommerce-checkout-fix.md)
- [2026-06-25 log](../activity-log/2026/2026-06/2026-06-25.md)
