import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def reserve(self, quantity: int) -> bool:
        """Atomically set aside `quantity` items.

        Returns True only if the stock could be decremented; the items are
        held for the caller so a later charge cannot oversell or ghost.
        """
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def release(self, quantity: int) -> None:
        """Return previously reserved items back to stock (e.g. payment failed)."""
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

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
