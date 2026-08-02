class OutOfStock(Exception):
    pass

class Inventory:
    def __init__(self, items=None):
        self.items = items if items is not None else {}

    def add(self, sku: str, qty: int) -> None:
        self.items[sku] = self.items.get(sku, 0) + qty

    def available(self, sku: str) -> int:
        return self.items.get(sku, 0)

    def reserve(self, sku: str, qty: int) -> None:
        if qty <= 0:
            raise ValueError("qty must be positive")
        if qty > self.items.get(sku, 0):
            raise OutOfStock(sku)
        self.items[sku] -= qty

    def release(self, sku: str, qty: int) -> None:
        if qty > self.available(sku):
            raise ValueError("Cannot release more than available")
        self.items[sku] -= qty