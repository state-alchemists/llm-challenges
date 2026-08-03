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
        async with self._lock:
            await asyncio.sleep(0.03)
            if random.random() < self._failure_rate:
                return False
            self.total_charged += amount
            self.charges.append({"order_id": order_id, "amount": amount})
            return True

    async def refund(self, order_id: str, amount: float) -> None:
        async with self._lock:
            await asyncio.sleep(0.01)
            # In a real gateway, we'd find the charge and reverse it
            self.total_charged -= amount
            # We keep the charge record for audit, or could remove it
            # For the simulation's 'total_charged' check, we must decrement
