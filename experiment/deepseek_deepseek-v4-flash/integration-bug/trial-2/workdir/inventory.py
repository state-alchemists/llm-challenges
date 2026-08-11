import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        # Guards stock mutations so check-and-decrement stays atomic
        # under concurrent checkouts.
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def reserve(self, quantity: int) -> bool:
        """Atomically check stock and hold ``quantity`` units.

        Returns True if the reservation succeeded (stock decremented),
        False if there is insufficient stock. A successful reservation
        must be released with :meth:`release` if the order is not
        completed, so the stock is returned.
        """
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def release(self, quantity: int) -> None:
        """Return reserved stock that was not sold."""
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

    async def decrement(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
