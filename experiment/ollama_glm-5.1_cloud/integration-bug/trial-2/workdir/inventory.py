import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

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

    async def reserve(self, quantity: int) -> bool:
        """Atomically check stock and decrement if available.

        This eliminates the TOCTOU race between check_stock and decrement
        by holding a lock across the entire operation.
        """
        async with self._lock:
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def release(self, quantity: int) -> None:
        """Return reserved stock back to inventory (e.g. after a failed charge)."""
        async with self._lock:
            self._stock += quantity

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
