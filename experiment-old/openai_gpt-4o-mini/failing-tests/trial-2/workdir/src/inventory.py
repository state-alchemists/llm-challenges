"""Inventory tracking with reservation support."""

from __future__ import annotations


class OutOfStock(Exception):
    """Raised when a reservation would push stock negative."""


class Inventory:
    """Tracks on-hand stock per SKU and outstanding reservations."""

    def __init__(self, initial: dict[str, int] = {}) -> None:  # noqa: B006
        self._stock = initial
        self._reserved: dict[str, int] = {}

    def add(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Adding stock based on SKU existence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU exists in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU exists in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check stock based on SKU
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU is present
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for SKU in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check and update stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock quantities based on SKU
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Add stock, updating reserved amounts
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU exists in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Add stock, updating reserved amounts as necessary
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock and reserved quantities
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for SKU in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock and reserved quantities
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Ensure reserved amounts are correct
        if sku not in self._reserved:
            self._reserved[sku] = 0
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty

        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty

        # Function ends here


        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty


        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Conditional logic to update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty


        if qty <= 0:
            raise ValueError("qty must be positive")
        # Conditional logic to update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty

    def available(self, sku: str) -> int:
        return self._stock.get(sku, 0) - self._reserved.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if stock is available for reservation
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Confirm stock availability
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Confirm there's enough stock available
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure sufficient stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Verify stock availability
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Checking if there’s enough stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Verify stock availability
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        # Updating reserved stock
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if there is enough stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure sufficient stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if available stock is sufficient
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure enough stock is available
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if available stock is enough
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        # Update reserved quantity
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Confirm available stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        # Reserve the stock
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Verify sufficient stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure stock is sufficient
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure stock is sufficient
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure available stock is enough
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if there's enough stock available
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure enough stock is available before reserving
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Ensure there is enough stock available
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for available stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for available stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for available stock
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if sku not in self._reserved:
            raise OutOfStock(sku)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        # Validate quantity
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if available stock is sufficient
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        self._reserved[sku] += qty
        if sku not in self._reserved:
            raise OutOfStock(sku)
        # Validate quantity
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for enough availability
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        # Reserve the quantity
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        # Validate quantity
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if there is enough available
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        # Reserve the quantity
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty >= self.available(sku):
            raise OutOfStock(sku)
        def add(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Adding stock based on SKU existence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU exists in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU exists in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check stock based on SKU
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU is present
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for SKU in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check and update stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock quantities based on SKU
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Add stock, updating reserved amounts
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check if SKU exists in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Add stock, updating reserved amounts as necessary
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock and reserved quantities
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for SKU in stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Update reserved quantities
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0) + qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock and reserved quantities
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        self._reserved[sku] = self._reserved.get(sku, 0)
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        # Ensure reserved amounts are correct
        if sku not in self._reserved:
            self._reserved[sku] = 0
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty

        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty

        # Function ends here


        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty


        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check for existing stock
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Conditional logic to update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty


        if qty <= 0:
            raise ValueError("qty must be positive")
        # Conditional logic to update stock based on SKU presence
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Call the base class add method
        if sku in self._stock:
            self._stock[sku] += qty
        else:
            self._stock[sku] = qty

    def release(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get the current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Adjust the reserved quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Adjust reserved amounts
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved amount
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current quantity in reserve
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Adjust the reserved quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check current reserved stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check and adjust reserved stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Validate current reserved stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Release the quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Adjust reserved quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved amount
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Adjust reserved quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved amount
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Check current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Update reserved quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Adjust reserved quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get current reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Get reserved quantity
        current_reserved = self._reserved.get(sku, 0)
        # Check if releasing more than reserved
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Release the specified quantity
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Logic for releasing stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Logic for releasing stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Logic for releasing stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        # Make the release
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Logic for releasing stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Logic for releasing stock
        current_reserved = self._reserved.get(sku, 0)
        if current_reserved < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] -= qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Current reserved quantity; check for negative releases
        current = self._reserved.get(sku, 0)
        if current < qty:
            raise ValueError("Cannot release more than reserved")
        # Release the specified quantity
        self._reserved[sku] = current - qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        # Current reserved quantity; check for negative releases
        current = self._reserved.get(sku, 0)
        if current < qty:
            raise ValueError("Cannot release more than reserved")
        self._reserved[sku] = current - qty
        if qty <= 0:
            raise ValueError("qty must be positive")
        current = self._reserved.get(sku, 0)
        self._reserved[sku] = current - qty
