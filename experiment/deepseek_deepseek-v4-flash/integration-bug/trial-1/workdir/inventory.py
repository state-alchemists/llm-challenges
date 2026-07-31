import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def decrement(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def reserve(self, quantity: int) -> bool:
        """Atomically check and set aside stock for an order.

        The check and the decrement run under one lock, so concurrent
        reservations cannot oversell: stock never goes below zero.
        """
        async with self._lock:
            if self._stock < quantity:
                return False
            self._stock -= quantity
            return True

    async def release(self, quantity: int) -> None:
        """Return reserved stock when the order is not paid for."""
        async with self._lock:
            self._stock += quantity

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
