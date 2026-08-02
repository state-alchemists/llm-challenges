import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        # Guards check+decrement as one atomic operation so concurrent
        # reservations can never oversell.
        self._lock = asyncio.Lock()

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

    async def reserve(self, quantity: int) -> bool:
        """Atomically check and decrement stock.

        Unlike check_stock + decrement, this is race-free: the check and the
        decrement happen under one lock with no interleaving, so inventory can
        never go below zero even under concurrent checkouts.
        """
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    @property
    def stock(self) -> int:
        return self._stock
