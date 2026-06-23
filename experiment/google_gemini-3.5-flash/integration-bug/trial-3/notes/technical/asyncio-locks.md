---
slug: asyncio-locks
---
# Asyncio Locks in Python

**Context:** Preventing race conditions in asyncio cooperative multitasking.
**Finding:** Even though Python's `asyncio` runs on a single thread, cooperative multitasking yields control at any `await` keyword. If a critical section spanning checks and updates contains `await` calls (e.g., waiting for sleep, external DB, payment gateway), other coroutines can run and violate invariants. An `asyncio.Lock` ensures that only one task can execute the critical section at any time.

**Source:** checkout.py

## Backlinks
- [Index](../index.md)
- [activity-log/2026/2026-06/2026-06-23](../activity-log/2026/2026-06/2026-06-23.md) — utilized to serialize checkout
