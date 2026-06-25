# Concurrent Inventory Checkout Pattern

## Problem

In concurrent checkout flows, the sequence `check stock → charge payment → decrement inventory` has a TOCTOU race:

1. Two concurrent orders both see `stock >= quantity` (pass check)
2. Both proceed to payment (both get charged)
3. One decrements first, the second decrement fails — but the customer was already charged
4. Or: concurrent decrements both pass the `>=` check before either writes — stock goes negative

## Solution: Reserve-then-Charge with Compensation

Replace the three-step sequence with an atomic **reservation** step:

```
try_reserve(quantity)   # atomic check + decrement under a lock
    → fail? return
charge(order_id, amount)
    → fail? release_reservation(quantity); return
# success — payment captured, stock already decremented
```

### Key properties

- **Atomic reservation**: A lock serializes concurrent check-and-decrement. Only one caller sees each unit of stock.
- **Rollback**: If payment fails, `release_reservation` returns stock to the pool.
- **No ghost charges**: Payment is only attempted after stock is secured. If payment succeeds, delivery is guaranteed.
- **Existing interfaces unchanged**: `check_stock` and `decrement` remain as-is (other callers may use them). New methods `try_reserve` and `release_reservation` are added.

### Trade-offs

- **Lock contention**: Under extreme concurrency, the lock serializes inventory access. For single-item stock this is fine; for bulk operations consider striped locks or optimistic concurrency.
- **No timeout on reservation**: In this implementation, a held reservation is released only on payment failure. A production system should add a reservation TTL to handle crashes between `try_reserve` and `charge`.

## See also

- [integration-bug-trial-3](../projects/integration-bug-trial-3.md) — actual implementation
- [2026-06-25 activity log](../activity-log/2026/2026-06/2026-06-25.md) — entry with verification results

## Backlinks

- [index](../index.md) — journal root
- [technical index](index.md) — directory index
- [2026-06-25 activity log](../activity-log/2026/2026-06/2026-06-25.md) — fix implemented and verified
- [integration-bug-trial-3 project](../projects/integration-bug-trial-3.md) — project applying this pattern
