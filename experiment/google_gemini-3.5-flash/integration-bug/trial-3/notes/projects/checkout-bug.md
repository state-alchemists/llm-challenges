---
slug: checkout-integration-concurrency-bug
---
# Checkout Integration Concurrency Bug

**Context:** Resolving concurrency issues in checkout flows where stock is checked, payments are charged, and stock is decremented.
**Finding:** Multiple concurrent checkout requests can concurrently pass stock checks, resulting in overallocation (overselling) and payment charges for items that cannot be delivered (ghost charges). This is resolved by serializing checkout transactions using an `asyncio.Lock` associated with each `Inventory` instance.
**Source:** checkout.py:12-38

## Backlinks
- [index](../index.md)
- [projects index](index.md)
- [2026-06-19 log](../activity-log/2026/2026-06/2026-06-19.md)
