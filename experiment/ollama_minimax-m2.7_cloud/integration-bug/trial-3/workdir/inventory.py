import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def get_stock(self) -> int:
        async with self._lock:
            return self._stock

    async def atomic_check_decrement(self, quantity: int) -> bool:
        """Atomically verify stock is sufficient and decrement it. Returns True if stock was decremented."""
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def atomic_increment(self, quantity: int) -> None:
        """Atomically restore stock (used when a prior atomic_check_decrement must be rolled back)."""
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

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
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
