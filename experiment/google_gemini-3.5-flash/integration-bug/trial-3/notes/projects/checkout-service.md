---
slug: checkout-service
---
# Checkout Service

**Context:** The checkout system managing concurrent inventory management and payments.
**Finding:** Checkout flow had race conditions leading to overselling and ghost charges because of check-then-act stock checks and deferred decrement.
**Source:** checkout.py:10

## Details
- Fixed by migrating to a **reservation-first (decrement-first)** pattern.
- If the payment fails or raises an exception during processing, the reserved inventory is immediately incremented back.

## Backlinks
- [Projects Index](index.md)
- [Distributed Transactions](../technical/distributed-transactions.md)
- [2026-06-25 activity log](../activity-log/2026/2026-06/2026-06-25.md)
