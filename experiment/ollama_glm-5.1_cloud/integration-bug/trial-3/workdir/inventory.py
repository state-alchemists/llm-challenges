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
            if self._stock >= quantity:
                self._stock -= quantity
                result = True
            else:
                result = False
        await asyncio.sleep(0.02)
        return result

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            self._stock += quantity
        await asyncio.sleep(0.01)

    async def release(self, quantity: int) -> None:
        """Return reserved stock when a downstream step (e.g. payment) fails."""
        async with self._lock:
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock