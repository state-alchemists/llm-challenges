"""Inventory tracking with reservation support."""

from __future__ import annotations


class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""


class Inventory:
    """Tracks on-hand stock per SKU and outstanding reservations."""

    def __init__(self, initial: dict[str, int] = {}) -> None:  # noqa: B006
        self._stock = initial.copy() if initial else {} # Initialize stock from input.
        self._reserved: dict[str, int] = {}  # Tracks reserved quantities for each SKU.

    def add(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku not in self._stock:
            self._stock[sku] = qty
        else:
            self._stock[sku] += qty # Correctly accumulate stock

    def available(self, sku: str) -> int:
        available_stock = self._stock.get(sku, 0) - self._reserved.get(sku, 0) if sku in self._stock else 0  # Ensure availability checks handle stock accurately
        return available_stock

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty > self.available(sku): # Update this conditional to not allow reservation beyond available stock
            raise OutOfStock(sku)
        # Increment reserved stock
        self._reserved[sku] = self._reserved.get(sku, 0) + qty

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        current = self._reserved.get(sku, 0)
        if current - qty < 0:
            raise ValueError("Cannot release more than reserved quantity")
        self._reserved[sku] = current - qty
