# Checkout Transaction Isolation

## Context
When multiple asynchronous checkouts execute concurrently:
1. "Overselling": Multiple coroutines check `stock >= quantity` and subsequently decrement it, bypassing the check and driving stock negative.
2. "Ghost charges": Payment goes through, but by the time decrement is called, stock is empty, leaving the user charged with no items.

## Solution
Instead of checking stock and then charging and then decrementing (which has a large race condition window during the payment charge), we use the **Reserve-then-Charge-or-Rollback** pattern:
1. Decrement stock first atomically. If it fails, return `False` (out of stock).
2. Attempt payment charging.
3. If charging succeeds, return `True` (successful transaction).
4. If charging fails, increment stock back to release the reservation and return `False`.

This guarantees:
- Stock never goes below zero.
- No ghost charges can occur.

## Backlinks
- [Technical Index](index.md)
