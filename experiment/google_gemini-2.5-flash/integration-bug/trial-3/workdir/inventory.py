import asyncio
from typing import Set


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()
        self._reserved_stock: Set[str] = set()  # To track reserved stock by order_id

    async def reserve_and_decrement(self, order_id: str, quantity: int) -> bool:
        async with self._lock:
            if order_id in self._reserved_stock:
                return False  # Already reserved for this order
            if self._stock >= quantity:
                self._stock -= quantity
                self._reserved_stock.add(order_id)
                await asyncio.sleep(0.02) # Simulate work
                return True
            return False

    async def release_reserved_stock(self, order_id: str, quantity: int) -> None:
        async with self._lock:
            if order_id in self._reserved_stock:
                self._stock += quantity
                self._reserved_stock.remove(order_id)
                await asyncio.sleep(0.01) # Simulate work

    # Existing methods, potentially updated to use the lock if needed for external calls.
    # For now, we'll assume external calls will use the new reserve_and_decrement/release_reserved_stock
    # or handle their own locking.
    async def check_stock(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)
            return self._stock >= quantity

    async def decrement(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
