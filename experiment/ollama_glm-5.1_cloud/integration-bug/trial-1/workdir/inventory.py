import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        async with self._lock:
            return self._stock >= quantity

    async def decrement(self, quantity: int) -> bool:
        async with self._lock:
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def reserve(self, quantity: int) -> bool:
        """Atomically check stock and decrement if available.

        Under a lock so no interleaving with other reservations.
        """
        async with self._lock:
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def restore(self, quantity: int) -> None:
        """Return reserved stock after a failed payment."""
        async with self._lock:
            self._stock += quantity

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock