# Checkout Service Project

## Overview
A concurrent checkout flow spanning user checkout, inventory management, and mock payment gateway.

## Structure
- `checkout.py` — handles coordinate-and-reserve logic.
- `inventory.py` — handles thread/coroutine-safe stock decrement/increment operations.
- `payments.py` — handles payment charging.

## Backlinks
- [Projects Index](index.md)
