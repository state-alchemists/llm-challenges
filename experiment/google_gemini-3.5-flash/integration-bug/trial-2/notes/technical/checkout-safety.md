---
slug: checkout-safety-patterns
---
# Checkout Safety Patterns

**Context:** Preventing overselling and ghost charges in concurrent e-commerce checkout systems.
**Finding:** A "Reserve-First, Charge-Next, Release-on-Failure" pattern ensures inventory and billing safety. By using an asynchronous mutex (`asyncio.Lock`) inside the inventory management service, checking/decrementing of stock becomes atomic, guaranteeing that stock levels never drop below zero. By billing only *after* a successful decrement (reservation), ghost charges are eliminated; if a subsequent charge fails, the reserved inventory is immediately returned (incremented back).
**Source:** checkout.py:6-25, inventory.py:6-26

## Backlinks
- [technical index](index.md)
- [2026-06-16 log](../activity-log/2026/2026-06/2026-06-16.md) — pattern implemented for checkout service
