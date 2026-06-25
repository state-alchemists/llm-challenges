import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        # This method is now only for external checks, the atomic decrement handles the actual reservation.
        # It's kept for interface compatibility but its direct use in checkout is discouraged for transactional integrity.
        return self._stock >= quantity

    async def decrement(self, quantity: int) -> bool:
        # This method is now only for internal use within atomic_decrement or specific, non-concurrent flows.
        if self._stock >= quantity:
            self._stock -= quantity
            return True
        return False

    async def increment(self, quantity: int) -> None:
        await asyncio.sleep(0.01) # Simulate async operation
        async with self._lock:
            self._stock += quantity

    async def atomic_decrement(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02) # Simulate async operation for stock check
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    @property
    def stock(self) -> int:
        return self._stock
