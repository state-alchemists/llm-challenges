import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)  # Simulate async operation
            return self._stock >= quantity

    async def decrement(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)  # Simulate async operation
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)  # Simulate async operation
            self._stock += quantity

    async def reserve_stock(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)  # Simulate async operation for check_stock
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def release_stock(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01) # Simulate async operation for increment
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
