---
slug: checkout-integration
---
# Checkout Integration Concurrency

**Context:** Concurrent checkouts where stock check, payment charge, and stock decrement occur in separate async steps can lead to race conditions (overselling and ghost charges).
**Finding:** By making stock decrement/increment methods concurrency-safe (using an `asyncio.Lock` bound to each inventory instance) and reserving stock *before* initiating the external charge, we guarantee that inventory never drops below zero and no customer is charged without stock reserved. If payment fails, the reserved stock is safely returned via an atomic increment.
**Source:** `checkout.py:1-30`, `inventory.py:1-30`

## Backlinks
- [2026-05-30 Activity Log](../activity-log/2026/2026-05/2026-05-30.md) — Fixed checkout overselling and ghost charge bugs.
