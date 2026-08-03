"""Inventory tracking with reservation support."""

from __future__ import annotations
from collections import defaultdict

class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""

class Inventory:
    """Tracks on-hand stock per SKU and outstanding reservations."""

    def __init__(self, initial: dict[str, int] = {}) -> None:
        self._stock = defaultdict(int, initial)
        self._reserved = defaultdict(int)

    def add(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        print(f"Adding {qty} of {sku}. Current stock: {self._stock[sku]}")
        self._stock[sku] += qty
        print(f"New stock: {self._stock[sku]}")

    def available(self, sku: str) -> int:
        return self._stock[sku] - self._reserved[sku]

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty > self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        current = self._reserved[sku]
        if current < qty:
            raise ValueError('Cannot release more than reserved')
        self._reserved[sku] -= qty
