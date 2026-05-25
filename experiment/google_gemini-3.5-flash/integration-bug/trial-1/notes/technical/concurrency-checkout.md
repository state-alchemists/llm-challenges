---
slug: concurrency-checkout
---
# Concurrency Checkout

**Context:** Concurrent checkouts with shared inventory and flaky payments.
**Finding:** Perform decrement (reservation) first under a Lock to prevent overselling and ghost charges, then process payment. If payment fails, increment back (revert reservation).
**Source:** checkout.py, inventory.py
