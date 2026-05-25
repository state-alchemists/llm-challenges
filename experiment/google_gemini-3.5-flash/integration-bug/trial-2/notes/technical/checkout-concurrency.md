---
slug: checkout-concurrency
---
# Checkout Concurrency Control

**Context:** Concurrent checkouts where stock check and decrement are separated by slow network/IO calls (like payment processing) can lead to overselling and ghost charges.
**Finding:** By introducing an `asyncio.Lock` inside the `Inventory` model and synchronizing the entire checkout process (checking stock, processing payment, and decrementing stock) within the lock, we prevent concurrent tasks from overlapping their critical section. This guarantees that stock never goes below zero, duplicate charges are avoided, and every successful payment corresponds to exactly one item decrement.
**Source:** checkout.py:12, inventory.py:7
