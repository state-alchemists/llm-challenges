---
slug: checkout-concurrency-fix
---
# Checkout Concurrency and Safe State Management

**Context:** High-concurrency checkout systems managing shared resources (inventory & payments).
**Finding:** Concurrently running checkouts with checking-before-decrement can lead to race conditions where stock becomes negative or customers get ghost-charged. Standardize on atomic stock decrement (reservation) before charging, and incrementing (releasing) back on payment failure. Use a concurrency lock (`asyncio.Lock`) inside the inventory class to make operations atomic.
**Source:** checkout.py:10, inventory.py:5

## Backlinks
- [2026-05-30 Activity Log](../activity-log/2026/2026-05/2026-05-30.md) — Solved overselling and ghost charges.
