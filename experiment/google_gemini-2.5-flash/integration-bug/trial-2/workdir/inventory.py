import asyncio


import asyncio


class Inventory:
    def __init__(self, stock: int):
        self._stock = stock
        self._lock = asyncio.Lock()  # Add a lock for atomic operations

    async def acquire_stock(self, order_id: str, quantity: int) -> bool:
        async with self._lock:
            await asyncio.sleep(0.02)  # Simulate async work
            if self._stock >= quantity:
                self._stock -= quantity
                print(f"Order {order_id}: acquired {quantity} items. Stock remaining: {self._stock}")
                return True
            print(f"Order {order_id}: failed to acquire {quantity} items. Stock remaining: {self._stock}")
            return False

    async def release_stock(self, order_id: str, quantity: int) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)  # Simulate async work
            self._stock += quantity
            print(f"Order {order_id}: released {quantity} items. Stock remaining: {self._stock}")

    # Remove check_stock and decrement as acquire_stock replaces them
    # The original increment method is kept, but it's not used in the checkout flow
    async def increment(self, quantity: int) -> None:
        async with self._lock: # Also lock increment to prevent race conditions
            await asyncio.sleep(0.01)
            self._stock += quantity

    @property
    def stock(self) -> int:
        return self._stock
