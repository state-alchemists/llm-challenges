---
slug: e-commerce-checkout
---
# E-Commerce Checkout Service Fix

**Context:** Production incidents reported overselling and ghost charges in the e-commerce checkout flow.
**Finding:** The original `checkout.py` had a race condition between `inventory.check_stock` and `inventory.decrement`, leading to negative inventory (overselling) under concurrent access. Ghost charges occurred because `gateway.charge` was called before `inventory.decrement`, and if `decrement` failed, the charge was not reversed or stock unreserved.
**Source:** User prompt, checkout.py, inventory.py, payments.py

## Backlinks
- [2026-07-31 Activity Log](activity-log/2026/2026-07/2026-07-31.md) — Fixed e-commerce checkout service