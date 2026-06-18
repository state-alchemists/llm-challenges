# Project: Checkout Integration Bug

This project tackles a race condition / integration bug in an e-commerce checkout flow where inventory goes negative (overselling) and duplicate/ghost charges occur.

## Key Facts
- Scaffolding files: `checkout.py`, `inventory.py`, `payments.py`, `main.py`.
- Solved by implementing an `asyncio.Lock()` per `Inventory` instance to synchronize checking, payment charging, and stock decrementing.

## Backlinks
- [Root](../index.md)
- [Projects Index](index.md)
- [2026-06-19 Log](../activity-log/2026/2026-06/2026-06-19.md)
