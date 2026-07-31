import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def _atomic_decrement(self, quantity: int) -> bool:
        async with self._lock:
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def reserve_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)  # Simulate async operation
        return await self._atomic_decrement(quantity)

    async def unreserve_stock(self, quantity: int) -> None:
        await asyncio.sleep(0.01)  # Simulate async operation
        async with self._lock:
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
