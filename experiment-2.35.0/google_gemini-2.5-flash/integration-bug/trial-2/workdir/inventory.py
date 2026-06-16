import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        # This method is now a simple read, not atomic for reservation
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def decrement(self, quantity: int) -> bool:
        # This method is now unsafe and should only be called after reservation
        # or by a method that holds the lock.
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

    async def reserve_item(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02) # Simulate async I/O for consistency
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    @property
    def stock(self) -> int:
        return self._stock
