import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock

    async def reserve(self, quantity: int) -> bool:
        """Atomically check and decrement stock. Returns True if reservation succeeded."""
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
