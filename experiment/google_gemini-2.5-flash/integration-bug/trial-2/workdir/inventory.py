import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()

    async def check_stock(self, quantity: int) -> bool:
        # This method is no longer used directly for critical path stock checks
        # It remains for other potential uses, but the atomic reserve method is preferred
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def reserve(self, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)  # Simulate async operation
            if self._stock >= quantity:
                self._stock -= quantity
                return True
            return False

    async def release(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)  # Simulate async operation
            self._stock += quantity

    async def decrement(self, quantity: int) -> bool:
        # This method should ideally not be called directly without prior reservation
        # For simplicity, we'll keep it locked if it were to be called.
        async with self._lock:
            await asyncio.sleep(0.02)
            if self._stock >= quantity:
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
