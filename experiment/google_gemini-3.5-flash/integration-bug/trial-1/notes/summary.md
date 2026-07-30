# Checkout Concurrency Integration Bug Fix

## Observations and Diagnostic
- Checked the original concurrent checkout flow in `checkout.py` and `inventory.py`.
- Identified that checking stock (`check_stock`) and decrementing stock (`decrement`) were split by a call to the mock payment gateway (`gateway.charge`), creating a large race condition window.
- Multiple concurrent checkouts could verify stock was available, then all call the payment gateway, leading to either overselling or ghost charges (where customers are charged but no stock is available to deliver the item).
- Additionally, `inventory.decrement` was not thread/coroutine-safe under async execution due to an `asyncio.sleep` preceding state changes without synchronization.

## Actions Taken
1. Added an `asyncio.Lock` to `Inventory` in `inventory.py` to serialize stock checking, decrementing, and incrementing.
2. Modified the checkout flow in `checkout.py` to use a reservation-first strategy:
   - Call `inventory.decrement` first to reserve stock before charging the customer.
   - If stock is not available, fail early before charging.
   - If payment fails, release the reservation by calling `inventory.increment`.
3. Verified the simulation with `main.py` and validated the solution using the official challenge validator `validator.py`, scoring an **EXCELLENT (1.0)** result.
