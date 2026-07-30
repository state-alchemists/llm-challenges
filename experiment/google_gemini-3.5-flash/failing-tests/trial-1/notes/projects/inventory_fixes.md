# Inventory Fixes

## Findings & Changes
- Fixed `Inventory.__init__` where a mutable default argument dictionary was shared across instances (`src/inventory.py:11-14`). Replaced it with a default `None` and instantiate a new dictionary `dict(initial) if initial is not None else {}`.
- Fixed `Inventory.add` to accumulate the stock quantities (`self._stock[sku] = self._stock.get(sku, 0) + qty`) instead of overwriting the stock (`src/inventory.py:16-19`).
- Fixed `Inventory.reserve` check from `qty >= self.available(sku)` to `qty > self.available(sku)` so users can reserve up to the available quantity (`src/inventory.py:21-26`).
- Fixed `Inventory.release` to validate that the quantity being released does not exceed the current outstanding reservation count (`src/inventory.py:28-34`).

## Backlinks
- [HUD Index](../index.md)
