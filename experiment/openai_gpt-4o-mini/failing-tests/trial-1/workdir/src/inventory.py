"""Inventory tracking with reservation support."""

from __future__ import annotations


class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""


class Inventory:
    """Tracks on-hand stock per SKU and outstanding reservations."""

    def __init__(self, initial: dict[str, int] = {}) -> None:  # noqa: B006
        self._stock = initial
        self._reserved: dict[str, int] = {}
        self._stock: dict[str, int] = {}

    def add(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku not in self._stock:
            self._stock[sku] = 0
        self._stock[sku] += qty

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0) - self._reserved.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty > self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0)

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        current = self._reserved.get(sku, 0)
        if qty > current:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty

