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

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        self._stock += quantity

    async def reserve(self, quantity: int) -> bool:
        """Atomically check and decrement stock. Guarded by a lock so
        concurrent checkouts cannot oversell."""
        async with self._lock:
            return await self.decrement(quantity)

    async def release(self, quantity: int) -> None:
        """Return a reservation to stock (e.g. when payment fails)."""
        async with self._lock:
            await self.increment(quantity)

    @property
    def stock(self) -> int:
        return self._stock
