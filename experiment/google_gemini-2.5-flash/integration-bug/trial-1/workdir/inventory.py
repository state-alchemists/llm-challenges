import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def try_decrement(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)  # Simulate I/O delay
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)  # Simulate I/O delay
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
