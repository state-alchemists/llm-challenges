"""Inventory tracking with reservation support."""

from __future__ import annotations

class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""

class Inventory:
    """Tracks on-hand stock per SKU and outstanding reservations."""

    def __init__(self, initial: dict[str, int] = {}) -> None:  # noqa: B006
        self._stock = dict(initial)
        print(f"Initialized Inventory with stock: {self._stock}")
        self._reserved: dict[str, int] = {}

    def add(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        print(f"Available for {sku}: {self._stock.get(sku, 0)} - {self._reserved.get(sku, 0)}")
        return self._stock.get(sku, 0) - self._reserved.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        available_stock = self.available(sku)
        print(f"Attempting to reserve {qty} of {sku}, available: {available_stock}")
        if qty > available_stock:
            raise OutOfStock(sku)
        self._stock[sku] -= qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        current = self._reserved.get(sku, 0)
        if qty > current:
            raise ValueError("cannot release more than reserved")
        self._reserved[sku] = current - qty
