import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def try_reserve(self, quantity: int) -> bool:
        """Atomically check and decrement stock. Returns True if reservation succeeded."""
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def release(self, quantity: int) -> None:
        """Restore stock (used when payment fails after reservation)."""
        await asyncio.sleep(0.01)
        self._stock += quantity

    async def decrement(self, quantity: int) -> bool:
        return await self.try_reserve(quantity)

    async def increment(self, quantity: int) -> None:
        await self.release(quantity)

    @property
    def stock(self) -> int:
        return self._stock
