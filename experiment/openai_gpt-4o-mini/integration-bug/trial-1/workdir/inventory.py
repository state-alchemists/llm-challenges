import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def hold(self, quantity: int) -> bool:
        """
        Hold items to ensure they are available for processing the order.
        Returns True if the hold was successful, False otherwise.
        """
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            return True
        return False

    async def decrement(self, quantity: int) -> bool:
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
