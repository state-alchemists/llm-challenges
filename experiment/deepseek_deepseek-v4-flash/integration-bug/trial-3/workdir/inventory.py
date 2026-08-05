import asyncio


class Inventory:
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

    async def reserve(self, quantity: int) -> bool:
        """Atomically take stock out of inventory.

        Safe under concurrent coroutines: the check and the decrement are
        contiguous (no await between them), so no other coroutine can
        interleave and stock can never go below zero.
        """
        await asyncio.sleep(0.02)
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def release(self, quantity: int) -> None:
        """Return reserved stock after a failed payment."""
        await asyncio.sleep(0.01)
        self._stock += quantity

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
