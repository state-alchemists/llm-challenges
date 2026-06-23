# Concurrency Patterns

## Atomic Reserve Pattern for Inventory Management

Fixes race conditions in concurrent checkout flows by inverting the operation order and using a lock-protected atomic operation.

### Problem

The naive flow `check_stock → charge → decrement` has two race windows:

1. **TOCTOU in `decrement`**: An `await` between method entry and the stock check means multiple coroutines all see the same `_stock` value and each decrement independently, driving stock negative.
2. **Charge-without-item**: A charge can succeed after `check_stock` passes, but the subsequent `decrement` fails because another order claimed the last unit during the decrement's sleep gap.

### Fix

1. **Atomic `reserve(quantity)`**: Check and decrement stock under `asyncio.Lock`, with the simulated latency *inside* the lock so concurrent access is serialized.
2. **Reserve-then-charge**: Reserve inventory first, then attempt payment. If payment fails, release the reservation via `increment()`. If payment succeeds, the item is already reserved — no path exists where a charge has no corresponding item.

```
reserve → charge → (on failure) increment
```

### Key properties

- Inventory never goes negative (atomic check-and-decrement)
- Every successful charge corresponds to exactly one reserved item
- No duplicate charges — each order calls `charge` exactly once per checkout
- No retry loops, no refunds needed

### Trade-off

`reserve` serializes all concurrent checkout attempts at the lock boundary. This is correct (contention on the last units is genuine) but means throughput at high concurrency is bounded by the lock's critical section duration.

## Backlinks
- [2026-06-23 activity](../activity-log/2026/2026-06/2026-06-23.md) — fix applied here
- [root index](../index.md)
- [technical index](index.md)
