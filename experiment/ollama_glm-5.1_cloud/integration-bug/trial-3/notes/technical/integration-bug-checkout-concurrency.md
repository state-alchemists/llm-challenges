---
slug: integration-bug-checkout-concurrency
---
# Integration Bug: Checkout Concurrency Fix

**Context:** E-commerce checkout service with overselling and ghost-charge production incidents.
**Finding:** Two TOCTOU race conditions and a missing idempotency guard in the async checkout flow:
1. `check_stock()` and `decrement()` are separate async calls — multiple coroutines pass the check before any decrements, causing overselling (stock goes negative).
2. If `charge()` succeeds but `decrement()` fails, the customer is charged with no item delivered (ghost charge) and no refund.
3. `PaymentGateway.charge()` records duplicate entries for the same `order_id` with no guard.

**Fix applied (three files, public interfaces preserved):**
- **`inventory.py`**: Added `asyncio.Lock` and `reserve(quantity)` method that atomically checks-and-decrements under the lock. Also protected `decrement()` with the same lock.
- **`payments.py`**: Added `_charged_ids` set for idempotency — `charge()` returns `True` immediately if the order was already charged, preventing duplicate records.
- **`checkout.py`**: Rewritten to reserve-then-charge: `reserve()` first, then `charge()`, then `increment()` (release reservation) on payment failure. Eliminates the TOCTOU window and ensures every successful charge corresponds to a delivered item.

**Source:** checkout.py, inventory.py, payments.py in workdir

## Backlinks