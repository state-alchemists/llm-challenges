import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()
        self._reservations = {} # New: Tracks order_id to reserved quantity

    async def check_stock(self, quantity: int) -> bool:
        # No lock needed for read-only check.
        # The actual stock decrement is protected by a lock in reserve_stock.
        await asyncio.sleep(0.02)
        return self._stock >= quantity

    async def reserve_stock(self, order_id: str, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02) # Simulate async operation
            if self._stock >= quantity:
                self._stock -= quantity
                self._reservations[order_id] = quantity
                return True
            return False

    async def release_stock(self, order_id: str) -> None:
        async with self._lock:
            await asyncio.sleep(0.02) # Simulate async operation
            if order_id in self._reservations:
                self._stock += self._reservations[order_id]
                del self._reservations[order_id]

    async def confirm_reservation(self, order_id: str) -> None:
        async with self._lock:
            await asyncio.sleep(0.01) # Simulate async operation
            if order_id in self._reservations:
                del self._reservations[order_id]

    async def increment(self, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
