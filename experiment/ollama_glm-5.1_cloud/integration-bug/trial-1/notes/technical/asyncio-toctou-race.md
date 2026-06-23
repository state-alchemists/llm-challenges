# TOCTOU Race in asyncio Checkout Flows

**Context**: E-commerce checkout service using `asyncio` with three stages: stock check → payment charge → stock decrement.

**Root cause**: The `checkout` function performed `check_stock()` → `gateway.charge()` → `inventory.decrement()` as separate `await`-yielding calls. Multiple concurrent coroutines all passed `check_stock` seeing the same stock level, proceeded to charge successfully, then fought over remaining stock in `decrement`. Those that lost the race were charged without receiving an item (ghost charges). Even though `decrement` re-checked stock, the charge had already been committed.

**Fix pattern — reserve-then-charge**:
1. `decrement` first (atomically reserve stock)
2. `charge` second (pay only if stock was secured)
3. `increment` on charge failure (rollback the reservation)

**Additional safeguards**:
- `asyncio.Lock` on `Inventory.decrement`/`increment` for atomicity beyond asyncio's cooperative scheduling
- Idempotency guard in `PaymentGateway.charge`: duplicate `order_id` returns True without double-charging

**Key insight**: In asyncio, operations between `await` points are atomic, but a multi-step business transaction that spans multiple `await`s is not. The fix eliminates the TOCTOU gap by making the stock reservation the first (and cheapest) operation, with rollback if the subsequent expensive operation (charge) fails.

## Backlinks
- [2026-06-23 log](../activity-log/2026/2026-06/2026-06-23.md) — diagnosed and fixed here