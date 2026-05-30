"""Inventory tracking with reservation support."""

from __future__ import annotations


class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""


class Inventory:
    def __init__(self, initial_stock: dict[str, int] | None = None):
        self.stock = initial_stock or {}
        self.reserved = {}

    def add(self, sku: str, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if sku in self.stock:
            self.stock[sku] += quantity
        else:
            self.stock[sku] = quantity

    def available(self, sku: str) -> int:
        return self.stock.get(sku, 0) - self.reserved.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty > self.available(sku):
            raise OutOfStock(sku)
        if sku in self.reserved:
            self.reserved[sku] += qty
        else:
            self.reserved[sku] = qty

    def release(self, sku: str, qty: int) -> None:
        current = self.reserved.get(sku, 0)
        if qty > current:
            raise ValueError("Cannot release more than reserved")
        if qty <= 0:
            raise ValueError("qty must be positive")
        current = self.reserved.get(sku, 0)
        self.reserved[sku] = current - qty
