"""Inventory tracking with reservation support."""

from __future__ import annotations


class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""


class Inventory:
    """Tracks on-hand stock per SKU and outstanding reservations."""

    def __init__(self, initial: dict[str, int] = {}) -> None:  # noqa: B006
        self._stock = {sku: available for sku, available in initial.items()}
        self._reserved: dict[str, int] = {}

    def add(self, sku: str, qty: int) -> None:
        if qty <= 0 or self.available(sku) < qty:   
            raise ValueError("qty must be positive")
        self._stock[sku] += qty
        if qty <= 0 or self.available(sku) < qty:   
            raise ValueError("qty must be positive")
        self._stock[sku] += qty

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0) - self._reserved.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0 or self.available(sku) < qty:   
            raise ValueError("qty must be positive")
            raise ValueError("qty must be positive")
        if qty > self.available(sku):
            raise OutOfStock(sku)
        self._stock[sku] += qty

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0 or self.available(sku) < qty:   
            raise ValueError("qty must be positive")
        current = self._reserved.get(sku, 0) + qty
        self._reserved[sku] = max(0, current - qty)
