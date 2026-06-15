import asyncio
import random
from typing import List


class PaymentGateway:
    def __init__(self, failure_rate: float = 0.25):
        self._failure_rate = failure_rate
        self.total_charged: float = 0.0
        self.charges: List[dict] = []
        self._lock = asyncio.Lock()

    async def charge(self, order_id: str, amount: float) -> bool:
        await asyncio.sleep(0.03)
        if random.random() < self._failure_rate:
            return False
        async with self._lock:
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            return True

    async def refund(self, order_id: str, amount: float) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            self.total_charged -= amount
            # For a simulation, simply remove the last charge for this order_id
            # In a real system, you'd match by a unique transaction ID
            for i, charge in enumerate(self.charges):
                if charge["order_id"] == order_id:
                    del self.charges[i]
                    break

