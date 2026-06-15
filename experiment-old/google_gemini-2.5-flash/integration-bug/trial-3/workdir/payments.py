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

    async def cancel_charge(self, order_id: str, amount: float) -> None:
        async with self._lock:
            # In a real system, this would involve calling the payment gateway API to reverse the charge.
            # For this simulation, we'll just adjust our internal records.
            self.total_charged -= amount
            self.charges = [c for c in self.charges if not (c["order_id"] == order_id and c["amount"] == amount)]
