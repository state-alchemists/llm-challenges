# Integration Bug Project

This project addresses two critical production issues in the E-Commerce Checkout Service:
1. **Overselling**: Items were being sold beyond stock capacity, resulting in negative inventory.
2. **Ghost Charges**: Payment was processed but no item was delivered because stock decrement failed after payment.

## Decisions
- Refactored `checkout.py` to use a reservation pattern: decrement stock before charging.
- Decrement is performed atomic-by-asyncio check.
- Succeeded charges guarantee successful delivery. Failed charges trigger a stock increment to return stock.
- Serialized concurrent requests using `asyncio.Lock` keyed by `order_id` to guarantee idempotency and prevent duplicate charges.

## Backlinks
- [index](../index.md)
