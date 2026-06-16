# Race condition in checkout flow

A classic concurrency race condition was identified in the checkout integration flow:
1. Stock checks and decrementing were non-atomic and un-synchronized, leading to overselling (inventory going negative) when multiple checkouts accessed stock concurrently.
2. Placing the third-party payment gateway call inside a lock blocks all checkouts sequentially, reducing throughput dramatically.
3. Placing the checkout steps in the sequence of check_stock -> charge -> decrement meant customers were charged but inventory checkouts could fail, leading to ghost charges.

## Solution: Reservation Pattern
1. Safe concurrency primitives: lock-guarded atomic decrement/increment inside the `Inventory` resource itself.
2. In `checkout`, reserve stock first by calling `inventory.decrement` (safe and non-blocking outside lock).
3. Attempt payment (`gateway.charge`) under `try...finally`.
4. If payment fails or an exception occurs, automatically release the reservation (`inventory.increment`) in the `finally` block.

## Backlinks
- [index](../index.md)
- [Technical Notes index](index.md)
- [2026-06-15 Log](../activity-log/2026/2026-06/2026-06-15.md)
