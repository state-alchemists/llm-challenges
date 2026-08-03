import asyncio

class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self.lock = asyncio.Lock()  # Lock for atomic operations

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def update_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        async with self.lock:  # Ensure atomic stock updates
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        async with self.lock:
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
