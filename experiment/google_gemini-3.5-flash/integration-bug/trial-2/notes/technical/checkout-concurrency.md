---
slug: checkout-concurrency
---
# Checkout Concurrency & Transactional Safety

**Context:** Applies when performing checkout sequences in Python `asyncio` applications that involve checking stock, charging users, and reserving/updating inventory.
**Finding:** Stock checks and stock decrements are vulnerable to race conditions when tasks yield execution (e.g. at `await asyncio.sleep(...)` or external API calls) between the check and the mutation. This results in negative stock (overselling) or paid-for items not being delivered (ghost charges). Implementing lock synchronization (`asyncio.Lock()`) around inventory mutation blocks solves this. Specifically, reserving inventory via an atomic `decrement` first under a lock, then attempting payment, and finally rolling back (incrementing) inventory if payment fails, maintains high concurrency and guarantees transactional safety.
**Source:** `checkout.py`, `inventory.py`

## Backlinks
- [index.md](../index.md) — Referenced as a recent insight
- [technical/index.md](index.md) — Referenced in technical index
- [activity-log/2026/2026-05/2026-05-30.md](../activity-log/2026/2026-05/2026-05-30.md) — Solved checkout bug
