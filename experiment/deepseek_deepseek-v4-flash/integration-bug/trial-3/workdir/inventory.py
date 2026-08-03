import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def decrement(self, quantity: int) -> bool:
        await asyncio.sleep(0.02)
        async with self._lock:
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01)
        async with self._lock:
            self._stock += quantity

    async def try_reserve(self, quantity: int) -> bool:
        """Atomically check and reserve stock, or return False without changing it.

        The check and the decrement happen under one lock so concurrent
        checkouts can never oversell: at most ``stock`` units are ever
        reserved, and a reservation is the only thing that lets a caller
        proceed to payment.
        """
        async with self._lock:
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    @property
    def stock(self) -> int:
        return self._stock
