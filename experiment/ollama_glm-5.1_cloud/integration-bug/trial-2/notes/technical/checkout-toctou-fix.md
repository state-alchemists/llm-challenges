---
slug: checkout-toctou-fix
---
# Checkout TOCTOU Race Fix

**Context:** E-commerce checkout with concurrent async orders (12 orders, 5 stock, 25% payment failure rate).
**Finding:** The original checkout flow was `check_stock → charge → decrement`. This TOCTOU race allowed all concurrent orders to pass `check_stock` before any `decrement` ran, causing: (1) overselling — more charges than stock, potentially negative inventory; (2) ghost charges — customers charged but `decrement` fails, returning False with no refund. The fix reorders to `decrement → charge → increment-on-failure`. Since `decrement`'s check-and-write has no `await` between them, it's atomic under asyncio, so stock never goes below zero. If `charge` fails, `increment` restores the reserved stock. No changes to `Inventory` or `PaymentGateway` public interfaces were needed.
**Source:** checkout.py:8-25, inventory.py:13-18