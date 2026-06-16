import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._locked = False

    async def lock(self):
        if not self._locked:
            self._locked = True
            return True
        return False

    async def unlock(self):
        if self._locked:
            self._locked = False

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity and not self._locked

    async def decrement(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        if self._stock >= quantity and not self._locked:
            self._stock -= quantity
            return True
        return False

    def __init__(self, stock: int):
        self._stock = stock

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

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
