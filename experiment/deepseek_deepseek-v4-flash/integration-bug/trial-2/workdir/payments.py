import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()

    def is_charged(self, order_id: str) -> bool:
        return any(c["order_id"] == order_id for c in self.charges)

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        async with self._lock:
            # Idempotency guard: an order is never charged more than once,
            # even if checkout is retried for the same order_id.
            if self.is_charged(order_id):
                return False
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            return True
