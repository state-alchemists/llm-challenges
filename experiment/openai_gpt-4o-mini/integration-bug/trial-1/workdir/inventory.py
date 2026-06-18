import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def safely_decrement(self, quantity: int) -> bool:
        print(f"Inventory before decrementing: {self._stock}, trying to decrement: {quantity}")
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            print(f"Inventory after decrementing: {self._stock}")
            return True
        print(f"Inventory not enough to decrement: {self._stock}")
        return False
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def decrement(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return await self.safely_decrement(quantity)
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
