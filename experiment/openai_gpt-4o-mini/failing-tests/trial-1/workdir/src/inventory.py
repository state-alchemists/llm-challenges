"""Inventory tracking with reservation support."""

from __future__ import annotations


class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""


class Inventory:
    """Tracks on-hand stock per SKU and outstanding reservations."""

    def __init__(self, initial: dict[str, int] = None) -> None:
        if initial is None:
            initial = {}

        self._stock = initial.copy()  # Make a copy of the initial stock
        self._reserved: dict[str, int] = {}  # noqa: B006
        self._stock = initial
        self._reserved: dict[str, int] = {}

    def add(self, sku: str, qty: int) -> None:
        print(f"Before adding: {sku} - Current stock: {self._stock}")
        if qty <= 0:
            raise ValueError("qty must be positive")
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        print(f"Checking available stock for: {sku} - Current stock: {self._stock}, Reserved: {self._reserved}")
        return self._stock.get(sku, 0) - self._reserved.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty > self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        current = self._reserved.get(sku, 0)
        if current < qty: raise ValueError("Cannot release more than reserved")
        self._reserved[sku] = current - qty
