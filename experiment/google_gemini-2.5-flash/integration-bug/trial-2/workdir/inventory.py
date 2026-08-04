import asyncio


import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)
            return self._stock >= quantity

    async def try_reserve_stock(self, order_id: str, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def release_reserved_stock(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

    async def decrement(self, quantity: int) -> bool:
        # This method is not used directly by checkout anymore but kept for interface contract
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity: # This check is redundant with try_reserve_stock.
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
